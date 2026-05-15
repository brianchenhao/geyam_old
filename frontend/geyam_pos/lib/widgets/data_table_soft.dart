import 'package:flutter/material.dart';

/// Soft data table matching the light-mode reference: compact rows, optional
/// soft-purple highlight on one column, subtle row dividers, rounded shell.
///
/// Use for transactions lists, inventory lists, purchase order lines, etc.
class DataTableSoft extends StatelessWidget {
  final List<String> columns;
  final List<List<Widget>> rows;

  /// Index of a column to tint with a soft purple highlight (per reference).
  /// Pass null to disable.
  final int? highlightColumn;

  /// Called when a row is tapped. Receives the row index.
  final void Function(int index)? onRowTap;

  /// Minimum width before the table becomes horizontally scrollable.
  final double minWidth;

  const DataTableSoft({
    super.key,
    required this.columns,
    required this.rows,
    this.highlightColumn,
    this.onRowTap,
    this.minWidth = 560,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final border = isDark
        ? Colors.white.withValues(alpha: 0.12)
        : Colors.black.withValues(alpha: 0.08);
    final highlight = isDark
        ? const Color(0xFF1E90FF).withValues(alpha: 0.14)
        : const Color(0xFFEDE9FE);
    final headerBg = isDark
        ? Colors.white.withValues(alpha: 0.04)
        : const Color(0xFFFAFAFA);

    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).cardTheme.color,
        border: Border.all(color: border, width: 1),
        borderRadius: BorderRadius.circular(16),
      ),
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final needsHScroll = constraints.maxWidth < minWidth;
          final tableWidth =
              needsHScroll ? minWidth : constraints.maxWidth;

          final tableBody = SizedBox(
            width: tableWidth,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  color: headerBg,
                  padding: const EdgeInsets.symmetric(
                      horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      for (var i = 0; i < columns.length; i++)
                        Expanded(
                          child: Text(
                            columns[i].toUpperCase(),
                            style: TextStyle(
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                              letterSpacing: 0.6,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withValues(alpha: 0.7),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                for (var r = 0; r < rows.length; r++)
                  InkWell(
                    onTap: onRowTap == null ? null : () => onRowTap!(r),
                    child: Container(
                      decoration: BoxDecoration(
                        border: Border(
                          top: BorderSide(color: border, width: 1),
                        ),
                      ),
                      padding: const EdgeInsets.symmetric(
                          horizontal: 16, vertical: 12),
                      child: Row(
                        children: [
                          for (var c = 0; c < rows[r].length; c++)
                            Expanded(
                              child: Container(
                                color:
                                    c == highlightColumn ? highlight : null,
                                padding: const EdgeInsets.symmetric(
                                    vertical: 4, horizontal: 6),
                                child: DefaultTextStyle.merge(
                                  style:
                                      Theme.of(context).textTheme.bodyMedium!,
                                  child: rows[r][c],
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          );

          final vertical = SingleChildScrollView(child: tableBody);
          return Scrollbar(
            child: needsHScroll
                ? SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: vertical,
                  )
                : vertical,
          );
        },
      ),
    );
  }
}
