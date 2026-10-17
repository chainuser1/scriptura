#ifndef RUNNER_FLUTTER_WINDOW_H_
#define RUNNER_FLUTTER_WINDOW_H_

#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>
#include <flutter/method_channel.h>
#include <shellapi.h>

#include <memory>

#include "win32_window.h"

// A window that does nothing but host a Flutter view.
class FlutterWindow : public Win32Window {
 public:
  // Creates a new FlutterWindow hosting a Flutter view running |project|.
  explicit FlutterWindow(const flutter::DartProject& project);
  virtual ~FlutterWindow();

 protected:
  // Win32Window:
  bool OnCreate() override;
  void OnDestroy() override;
  LRESULT MessageHandler(HWND window, UINT const message, WPARAM const wparam,
                         LPARAM const lparam) noexcept override;

 private:
  // The project to run.
  flutter::DartProject project_;

  // The Flutter instance hosted by this window.
  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;

  // Quick search from anywhere: Ctrl+Alt+Space brings the window forward with the quick search open. With
  // [background_] on, closing the window hides it to the tray so the shortcut keeps working; Quit in the tray menu ends it.
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> channel_;
  bool background_ = false;
  bool hotkey_ = false;
  bool tray_ = false;
  NOTIFYICONDATA tray_icon_{};
  void ShowTray(bool on);
  void BringToFront();
};

#endif  // RUNNER_FLUTTER_WINDOW_H_
