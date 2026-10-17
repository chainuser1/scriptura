#include "flutter_window.h"

#include <optional>

#include <flutter/standard_method_codec.h>

#include "flutter/generated_plugin_registrant.h"
#include "resource.h"

namespace {
constexpr int kHotkeyId = 1;
constexpr UINT kTrayMessage = WM_APP + 1;
constexpr UINT kMenuOpen = 1, kMenuQuit = 2;
const UINT kTaskbarCreated = RegisterWindowMessage(L"TaskbarCreated");  // Explorer restarted: the tray icon is gone
}  // namespace

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());

  channel_ = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "scriptura/desktop", &flutter::StandardMethodCodec::GetInstance());
  channel_->SetMethodCallHandler([this](const auto& call, auto result) {
    if (call.method_name() != "configure") return result->NotImplemented();
    const auto* args = std::get_if<flutter::EncodableMap>(call.arguments());
    if (args) {
      auto it = args->find(flutter::EncodableValue("background"));
      if (it != args->end()) background_ = std::get<bool>(it->second);
    }
    ShowTray(background_);
    result->Success(flutter::EncodableValue(flutter::EncodableMap{{flutter::EncodableValue("hotkey"), flutter::EncodableValue(hotkey_)}}));
  });
  hotkey_ = RegisterHotKey(GetHandle(), kHotkeyId, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, VK_SPACE);
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  flutter_controller_->engine()->SetNextFrameCallback([&]() {
    this->Show();
  });

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  UnregisterHotKey(GetHandle(), kHotkeyId);
  ShowTray(false);
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  if (message == kTaskbarCreated && tray_) {
    tray_ = false;
    ShowTray(true);
  }

  switch (message) {
    case WM_HOTKEY:
      if (wparam == kHotkeyId) {
        BringToFront();
        if (channel_) channel_->InvokeMethod("quickSearch", nullptr);
        return 0;
      }
      break;
    case WM_CLOSE:
      if (background_) {
        ShowWindow(hwnd, SW_HIDE);
        return 0;
      }
      break;
    case kTrayMessage:
      if (LOWORD(lparam) == WM_LBUTTONUP) BringToFront();
      if (LOWORD(lparam) == WM_RBUTTONUP || LOWORD(lparam) == WM_CONTEXTMENU) {
        HMENU menu = CreatePopupMenu();
        AppendMenu(menu, MF_STRING, kMenuOpen, L"Open Scriptura");
        AppendMenu(menu, MF_STRING, kMenuQuit, L"Quit");
        POINT at;
        GetCursorPos(&at);
        SetForegroundWindow(hwnd);  // so the menu closes when the user clicks elsewhere
        const UINT pick = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, at.x, at.y, 0, hwnd, nullptr);
        DestroyMenu(menu);
        if (pick == kMenuOpen) BringToFront();
        if (pick == kMenuQuit) {
          background_ = false;
          PostMessage(hwnd, WM_CLOSE, 0, 0);
        }
      }
      return 0;
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}

void FlutterWindow::ShowTray(bool on) {
  if (on == tray_) return;
  tray_icon_.cbSize = sizeof(tray_icon_);
  tray_icon_.hWnd = GetHandle();
  tray_icon_.uID = 1;
  if (on) {
    tray_icon_.uFlags = NIF_ICON | NIF_MESSAGE | NIF_TIP;
    tray_icon_.uCallbackMessage = kTrayMessage;
    tray_icon_.hIcon = LoadIcon(GetModuleHandle(nullptr), MAKEINTRESOURCE(IDI_APP_ICON));
    wcscpy_s(tray_icon_.szTip, L"Scriptura: Ctrl+Alt+Space to search");
    tray_ = Shell_NotifyIcon(NIM_ADD, &tray_icon_);
  } else {
    Shell_NotifyIcon(NIM_DELETE, &tray_icon_);
    tray_ = false;
  }
}

void FlutterWindow::BringToFront() {
  HWND hwnd = GetHandle();
  if (!hwnd) return;
  ShowWindow(hwnd, IsIconic(hwnd) ? SW_RESTORE : SW_SHOW);
  SetForegroundWindow(hwnd);
}
