import 'dart:typed_data';

Future<void> platformDownload({
  required Uint8List bytes,
  required String filename,
  required String mimeType,
}) async {
  throw UnsupportedError(
      'File download is currently web-only. Open this page in a browser to export.');
}
