import 'package:flutter/material.dart';

class CartItem {
  final int menuItemId;
  final String name;
  final double price;
  final double? confidence;
  int quantity;

  CartItem({
    required this.menuItemId,
    required this.name,
    required this.price,
    required this.quantity,
    this.confidence,
  });

  double get lineTotal => price * quantity;
}

class CartWidget extends StatelessWidget {
  final List<CartItem> items;
  final void Function(int index) onRemove;
  final void Function(int index, int delta) onQtyChange;

  const CartWidget({
    super.key,
    required this.items,
    required this.onRemove,
    required this.onQtyChange,
  });

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text('Cart is empty. Tap the camera to scan a tray.'),
        ),
      );
    }
    return ListView.separated(
      itemCount: items.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final item = items[i];
        return ListTile(
          title: Text(item.name),
          subtitle: Text(
            'RM ${item.price.toStringAsFixed(2)}'
            '${item.confidence != null ? '  ·  ${(item.confidence! * 100).toStringAsFixed(0)}%' : ''}',
          ),
          trailing: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                icon: const Icon(Icons.remove_circle_outline),
                onPressed: () => onQtyChange(i, -1),
              ),
              SizedBox(
                width: 24,
                child: Text('${item.quantity}', textAlign: TextAlign.center),
              ),
              IconButton(
                icon: const Icon(Icons.add_circle_outline),
                onPressed: () => onQtyChange(i, 1),
              ),
              IconButton(
                icon: const Icon(Icons.delete_outline),
                onPressed: () => onRemove(i),
              ),
            ],
          ),
        );
      },
    );
  }
}
