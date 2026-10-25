/// The version this build reports. Keep equal to `version:` in pubspec.yaml (tool/make_release.py refuses to stage a
/// release when they differ).
const String kAppVersion = '1.0.9';

/// GitHub's "latest release" endpoint for this project, for example
/// `https://api.github.com/repos/<owner>/<repo>/releases/latest`. Empty until the repository is public; while it is
/// empty the app shows no update check at all (it never contacts a server it was not given).
const String kReleasesApi = 'https://api.github.com/repos/chainuser1/scriptura/releases/latest';
