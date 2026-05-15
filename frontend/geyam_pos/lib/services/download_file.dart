import 'dart:typed_data';

import 'download_file_stub.dart'
    if (dart.library.html) 'download_file_web.dart';

/// Trigger a "save file" prompt in the user's browser (web) or throw a
/// helpful error on non-web platforms. Mobile/desktop will need their own
/// implementation (e.g. `share_plus`) when those platforms ship reports.
Future<void> downloadFile({
  required Uint8List bytes,
  required String filename,
  required String mimeType,
}) =>
    platformDownload(bytes: bytes, filename: filename, mimeType: mimeType);
