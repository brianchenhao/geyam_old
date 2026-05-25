import 'package:flutter/material.dart';

import '../services/api_service.dart';

class AskChatBubble extends StatefulWidget {
  const AskChatBubble({super.key});

  @override
  State<AskChatBubble> createState() => _AskChatBubbleState();
}

class _ChatMsg {
  final String text;
  final bool fromUser;
  final bool isError;
  _ChatMsg(this.text, {required this.fromUser, this.isError = false});
}

class _AskChatBubbleState extends State<AskChatBubble> {
  bool _open = false;
  bool _sending = false;
  final List<_ChatMsg> _msgs = [];
  final TextEditingController _ctrl = TextEditingController();
  final ScrollController _scroll = ScrollController();

  @override
  void dispose() {
    _ctrl.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final q = _ctrl.text.trim();
    if (q.isEmpty || _sending) return;
    setState(() {
      _msgs.add(_ChatMsg(q, fromUser: true));
      _ctrl.clear();
      _sending = true;
    });
    _scrollToEnd();
    try {
      final r = await ApiService.post('/ask', body: {'question': q});
      final answer = (r is Map && r['answer'] != null)
          ? r['answer'].toString()
          : (r?.toString() ?? '(no answer)');
      if (!mounted) return;
      setState(() => _msgs.add(_ChatMsg(answer, fromUser: false)));
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _msgs.add(_ChatMsg(
            "Couldn't reach the LLM (${e.statusCode}). Is the backend running and the LLM endpoint reachable?",
            fromUser: false,
            isError: true,
          )));
    } catch (e) {
      if (!mounted) return;
      setState(() => _msgs.add(_ChatMsg('Error: $e', fromUser: false, isError: true)));
    } finally {
      if (mounted) setState(() => _sending = false);
      _scrollToEnd();
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Positioned(
      left: 16,
      bottom: 16,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_open) _popup(cs),
          if (_open) const SizedBox(height: 12),
          _circle(cs),
        ],
      ),
    );
  }

  Widget _circle(ColorScheme cs) {
    return Material(
      color: cs.primary,
      shape: const CircleBorder(),
      elevation: 6,
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: () => setState(() => _open = !_open),
        child: SizedBox(
          width: 56,
          height: 56,
          child: Icon(
            _open ? Icons.close : Icons.chat_bubble_outline,
            color: cs.onPrimary,
            size: 26,
          ),
        ),
      ),
    );
  }

  Widget _popup(ColorScheme cs) {
    final screen = MediaQuery.of(context).size;
    final w = screen.width < 340 + 32 ? screen.width - 32 : 340.0;
    final h = screen.height < 440 + 120 ? screen.height - 120 : 440.0;
    return Material(
      elevation: 10,
      borderRadius: BorderRadius.circular(16),
      color: cs.surface,
      child: Container(
        width: w,
        height: h,
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: cs.outlineVariant.withValues(alpha: 0.4)),
        ),
        child: Column(
          children: [
            _header(cs),
            const Divider(height: 1),
            Expanded(child: _list(cs)),
            const Divider(height: 1),
            _input(cs),
          ],
        ),
      ),
    );
  }

  Widget _header(ColorScheme cs) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 8, 10),
      child: Row(
        children: [
          Icon(Icons.auto_awesome, color: cs.primary, size: 18),
          const SizedBox(width: 8),
          const Text('Ask GEYAM', style: TextStyle(fontWeight: FontWeight.w600)),
          const Spacer(),
          IconButton(
            icon: const Icon(Icons.close, size: 18),
            onPressed: () => setState(() => _open = false),
          ),
        ],
      ),
    );
  }

  Widget _list(ColorScheme cs) {
    if (_msgs.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(20),
        child: Text(
          'Ask about your sales, top items, or forecasts.\n\n'
          'e.g. "What was revenue last week?"\n'
          'or "Predict tomorrow\'s sales."',
          style: TextStyle(color: cs.onSurfaceVariant, fontSize: 13, height: 1.5),
        ),
      );
    }
    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.all(12),
      itemCount: _msgs.length + (_sending ? 1 : 0),
      itemBuilder: (_, i) {
        if (i == _msgs.length) return _typing(cs);
        final m = _msgs[i];
        return Align(
          alignment: m.fromUser ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.symmetric(vertical: 4),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            constraints: const BoxConstraints(maxWidth: 260),
            decoration: BoxDecoration(
              color: m.fromUser
                  ? cs.primary
                  : (m.isError ? cs.errorContainer : cs.surfaceContainerHighest),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              m.text,
              style: TextStyle(
                color: m.fromUser
                    ? cs.onPrimary
                    : (m.isError ? cs.onErrorContainer : cs.onSurface),
                fontSize: 13,
                height: 1.35,
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _typing(ColorScheme cs) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: cs.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(12),
        ),
        child: SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(strokeWidth: 2, color: cs.primary),
        ),
      ),
    );
  }

  Widget _input(ColorScheme cs) {
    return Padding(
      padding: const EdgeInsets.all(8),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _ctrl,
              enabled: !_sending,
              onSubmitted: (_) => _send(),
              decoration: const InputDecoration(
                hintText: 'Ask anything…',
                isDense: true,
                border: OutlineInputBorder(),
                contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              ),
            ),
          ),
          const SizedBox(width: 6),
          IconButton(
            icon: const Icon(Icons.send),
            color: cs.primary,
            onPressed: _sending ? null : _send,
          ),
        ],
      ),
    );
  }
}
