import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../services/api_service.dart';
import '../widgets/app_drawer.dart';
import '../widgets/data_table_soft.dart';
import '../widgets/geyam_leading.dart';
import '../widgets/section_card.dart';
import 'csv_preview_screen.dart';

class MenuManagerScreen extends StatefulWidget {
  const MenuManagerScreen({super.key});

  @override
  State<MenuManagerScreen> createState() => _MenuManagerScreenState();
}

class _MenuManagerScreenState extends State<MenuManagerScreen> {
  List<dynamic> _items = [];
  bool _loading = true;
  String? _error;
  bool _includeArchived = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = null; });
    try {
      final q = _includeArchived ? {'include_archived': 'true'} : <String, String>{};
      final r = await ApiService.get('/menu', query: q);
      setState(() { _items = (r is List) ? r : []; _loading = false; });
    } catch (e) {
      setState(() { _error = e is ApiException ? e.message : e.toString(); _loading = false; });
    }
  }

  Future<void> _editDialog({Map? item}) async {
    final isEdit = item != null;
    final name = TextEditingController(text: item?['name']?.toString() ?? '');
    final price = TextEditingController(text: item?['price']?.toString() ?? '');
    final category = TextEditingController(text: item?['category']?.toString() ?? '');
    final stock = TextEditingController(text: item?['stock_qty']?.toString() ?? '0');
    final reorder = TextEditingController(text: item?['reorder_point']?.toString() ?? '0');

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(isEdit ? 'Edit item' : 'New item'),
        content: SizedBox(
          width: 400,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(controller: name, decoration: const InputDecoration(labelText: 'Name')),
              TextField(controller: price, decoration: const InputDecoration(labelText: 'Price (RM)'), keyboardType: TextInputType.number),
              TextField(controller: category, decoration: const InputDecoration(labelText: 'Category')),
              TextField(controller: stock, decoration: const InputDecoration(labelText: 'Stock qty'), keyboardType: TextInputType.number),
              TextField(controller: reorder, decoration: const InputDecoration(labelText: 'Reorder point'), keyboardType: TextInputType.number),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Save')),
        ],
      ),
    );
    if (ok != true) return;

    final body = {
      'name': name.text.trim(),
      'price': double.tryParse(price.text.trim()) ?? 0.0,
      'category': category.text.trim(),
      'stock_qty': int.tryParse(stock.text.trim()) ?? 0,
      'reorder_point': int.tryParse(reorder.text.trim()) ?? 0,
    };
    try {
      if (isEdit) {
        await ApiService.patch('/menu/${item['id']}', body: body);
      } else {
        await ApiService.post('/menu', body: body);
      }
      await _load();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  Future<void> _uploadImage(Map item) async {
    final xf = await ImagePicker().pickImage(source: ImageSource.gallery, maxWidth: 2048);
    if (xf == null) return;
    final bytes = await xf.readAsBytes();
    try {
      await ApiService.uploadBytes(
        '/menu/${item['id']}/image',
        bytes: bytes,
        filename: xf.name,
        contentType: 'image/png',
      );
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _softDelete(Map item) async {
    try {
      await ApiService.delete('/menu/${item['id']}');
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _restore(Map item) async {
    try {
      await ApiService.post('/menu/${item['id']}/restore');
      await _load();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _pickCsv() async {
    final r = await FilePicker.platform.pickFiles(
      type: FileType.custom, allowedExtensions: ['csv'], withData: true,
    );
    if (r == null || r.files.isEmpty) return;
    final f = r.files.first;
    final bytes = f.bytes;
    if (bytes == null) return;
    if (!mounted) return;
    final imported = await Navigator.of(context).push<bool>(MaterialPageRoute(
      builder: (_) => CsvPreviewScreen(bytes: bytes, filename: f.name),
    ));
    if (imported == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      drawer: const AppDrawer(),
      appBar: AppBar(
        leading: const GeyamLeading(),
        leadingWidth: 96,
        title: const Text('Menu manager'),
        actions: [
          const Text('Archived'),
          Switch(value: _includeArchived, onChanged: (v) { setState(() => _includeArchived = v); _load(); }),
          IconButton(onPressed: _loading ? null : _load, icon: const Icon(Icons.refresh)),
          IconButton(onPressed: _pickCsv, icon: const Icon(Icons.upload_file), tooltip: 'Bulk CSV'),
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: FilledButton.icon(
              onPressed: () => _editDialog(),
              icon: const Icon(Icons.add),
              label: const Text('New item'),
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Text(_error!, style: const TextStyle(color: Colors.red)))
                : SectionCard(
                    fill: true,
                    title: '${_items.length} item(s)',
                    child: _items.isEmpty
                        ? const Padding(padding: EdgeInsets.all(24), child: Text('No items'))
                        : DataTableSoft(
                            columns: const ['Name', 'Category', 'Price', 'Stock', 'Active', 'Actions'],
                            highlightColumn: 2,
                            rows: [
                              for (final i in _items)
                                [
                                  Text(i['name']?.toString() ?? '?'),
                                  Text(i['category']?.toString() ?? ''),
                                  Text('RM ${i['price']}'),
                                  Text('${i['stock_qty']}'),
                                  Text(i['is_active'] == false ? 'archived' : 'active'),
                                  Row(mainAxisSize: MainAxisSize.min, children: [
                                    IconButton(icon: const Icon(Icons.image, size: 18), onPressed: () => _uploadImage(i as Map), tooltip: 'Upload image'),
                                    IconButton(icon: const Icon(Icons.edit, size: 18), onPressed: () => _editDialog(item: i as Map)),
                                    if (i['is_active'] == false)
                                      IconButton(icon: const Icon(Icons.restore, size: 18), onPressed: () => _restore(i as Map), tooltip: 'Restore')
                                    else
                                      IconButton(icon: const Icon(Icons.delete, size: 18), onPressed: () => _softDelete(i as Map)),
                                  ]),
                                ],
                            ],
                          ),
                  ),
      ),
    );
  }
}
