import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/theme_toggle.dart';

class ProductUploadScreen extends StatefulWidget {
  const ProductUploadScreen({super.key});

  @override
  State<ProductUploadScreen> createState() => _ProductUploadScreenState();
}

class _ProductUploadScreenState extends State<ProductUploadScreen> {
  final nameCtrl = TextEditingController();
  final priceCtrl = TextEditingController();
  XFile? video;
  bool uploading = false;
  String? message;

  Future<void> _pickVideo() async {
    final picker = ImagePicker();
    final picked = await picker.pickVideo(source: ImageSource.gallery);
    if (picked != null) setState(() => video = picked);
  }

  Future<void> _upload() async {
    final name = nameCtrl.text.trim();
    final price = double.tryParse(priceCtrl.text);
    if (name.isEmpty || price == null || price <= 0 || video == null) {
      setState(() => message = 'Need name, price > 0, and a video.');
      return;
    }
    setState(() {
      uploading = true;
      message = null;
    });
    try {
      final result = await ApiService.trainVideo(
        name: name,
        price: price,
        video: video!,
      );
      setState(() => message = 'Server: ${result['status'] ?? result.toString()}');
    } catch (e) {
      setState(() => message = 'Upload failed: $e');
    } finally {
      if (mounted) setState(() => uploading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Train new product'),
        actions: const [ThemeToggle()],
      ),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Product name',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: priceCtrl,
                  keyboardType:
                      const TextInputType.numberWithOptions(decimal: true),
                  decoration: const InputDecoration(
                    labelText: 'Price (RM)',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: _pickVideo,
                        icon: const Icon(Icons.video_file),
                        label: Text(video?.name ?? 'Pick video'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 24),
                if (message != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(message!),
                  ),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: uploading ? null : _upload,
                    child: uploading
                        ? const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Start training'),
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Training runs in the background on the server.\n'
                  'Check /model/status to see when it completes.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
