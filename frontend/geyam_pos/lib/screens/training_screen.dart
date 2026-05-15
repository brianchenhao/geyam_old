import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';

class TrainingScreen extends StatefulWidget {
  const TrainingScreen({super.key});

  @override
  State<TrainingScreen> createState() => _TrainingScreenState();
}

class _TrainingScreenState extends State<TrainingScreen> {
  List<dynamic> _jobs = [];
  List<dynamic> _items = [];
  Map<String, dynamic>? _modelStatus;
  bool _loading = true;
  bool _training = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final jobs = await ApiService.get('/train/jobs');
      final items = await ApiService.get('/menu');
      final ms = await ApiService.get('/model/status');
      setState(() {
        _jobs = (jobs is List) ? jobs : [];
        _items = (items is List) ? items : [];
        _modelStatus = (ms is Map<String, dynamic>) ? ms : null;
        _loading = false;
      });
    } catch (e) {
      setState(() { _error = e is ApiException ? e.message : e.toString(); _loading = false; });
    }
  }

  Future<void> _uploadVideo() async {
    final itemId = await showDialog<int>(
      context: context,
      builder: (ctx) {
        int? sel;
        return StatefulBuilder(builder: (ctx, setS) {
          return AlertDialog(
            title: const Text('Select menu item'),
            content: SizedBox(
              width: 400,
              child: DropdownButtonFormField<int>(
                value: sel,
                isExpanded: true,
                items: [
                  for (final i in _items)
                    DropdownMenuItem(value: i['id'] as int, child: Text(i['name']?.toString() ?? '?')),
                ],
                onChanged: (v) => setS(() => sel = v),
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
              FilledButton(onPressed: sel == null ? null : () => Navigator.pop(ctx, sel), child: const Text('Pick video')),
            ],
          );
        });
      },
    );
    if (itemId == null) return;

    final xf = await ImagePicker().pickVideo(source: ImageSource.gallery, maxDuration: const Duration(seconds: 60));
    if (xf == null) return;
    final bytes = await xf.readAsBytes();
    try {
      await ApiService.uploadBytes(
        '/train/video',
        bytes: bytes,
        filename: xf.name,
        contentType: 'video/mp4',
        fields: {'menu_item_id': '$itemId'},
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Video queued')));
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _trainNow() async {
    setState(() => _training = true);
    try {
      await ApiService.post('/train/run');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Training started')));
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _training = false);
    }
  }

  String _itemName(int? id) {
    if (id == null) return '?';
    final m = _items.firstWhere((x) => x['id'] == id, orElse: () => null);
    return m == null ? '?' : (m['name']?.toString() ?? '?');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Training'),
        actions: [
          IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh)),
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Row(mainAxisSize: MainAxisSize.min, children: [
              OutlinedButton.icon(onPressed: _uploadVideo, icon: const Icon(Icons.video_file), label: const Text('Upload video')),
              const SizedBox(width: 8),
              FilledButton.icon(
                onPressed: _training ? null : _trainNow,
                icon: const Icon(Icons.play_arrow),
                label: Text(_training ? 'Training…' : 'Train now'),
              ),
            ]),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SectionCard(
                        title: 'Active model',
                        child: _activeModel(),
                      ),
                      const SizedBox(height: 16),
                      SectionCard(
                        title: '${_jobs.length} job(s)',
                        child: _jobs.isEmpty
                            ? const Text('No jobs yet — upload a 30s video of a product.')
                            : DataTableSoft(
                                columns: const ['Item', 'Status', 'Frames', 'Queued at', 'Error'],
                                rows: [
                                  for (final j in _jobs)
                                    [
                                      Text(_itemName(j['menu_item_id'] as int?)),
                                      Text(j['status']?.toString() ?? '?'),
                                      Text('${j['frames_extracted'] ?? '-'}'),
                                      Text(j['queued_at']?.toString().split('T').first ?? ''),
                                      Text(j['error']?.toString() ?? ''),
                                    ]
                                ],
                              ),
                      ),
                    ],
                  ),
                ),
    );
  }

  Widget _activeModel() {
    final a = _modelStatus?['active'];
    if (a == null) return const Text('No trained model yet.');
    final m = a as Map;
    final acc = m['accuracy'];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text('File: ${m['filename'] ?? '?'}'),
      Text('Classes: ${m['num_classes'] ?? 0}'),
      Text('Accuracy (mAP50): ${acc == null ? '-' : (acc as num).toStringAsFixed(3)}'),
      Text('Trained at: ${m['trained_at']?.toString().replaceFirst('T', ' ').split('.').first ?? '?'}'),
      if (m['notes'] != null) Text('Notes: ${m['notes']}'),
    ]);
  }
}
