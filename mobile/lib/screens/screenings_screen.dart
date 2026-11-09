import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/local_store.dart';
import '../theme.dart';
import '../widgets/ui.dart';
import 'patient_screen.dart';
import 'result_screen.dart';
import 'wizard_screen.dart';

/// « Mes dépistages » : saisies de l'appareil (filtrables par niveau) et recherche de dossiers sur le serveur.
class ScreeningsScreen extends StatefulWidget {
  const ScreeningsScreen({super.key});
  @override
  State<ScreeningsScreen> createState() => _ScreeningsScreenState();
}

class _ScreeningsScreenState extends State<ScreeningsScreen> {
  List<LocalRecord> _screenings = [];
  String _filter = 'tous';
  final _search = TextEditingController();
  List<dynamic>? _serverResults;
  String? _searchInfo;
  Timer? _debounce;

  static const _filters = [
    ('tous', 'Tous'),
    ('eleve', 'Élevé'),
    ('moyen', 'Moyen'),
    ('faible', 'Faible'),
    ('attente', 'En attente'),
  ];

  @override
  void initState() {
    super.initState();
    _load();
    context.read<AppState>().addListener(_load);
  }

  @override
  void dispose() {
    context.read<AppState>().removeListener(_load);
    _debounce?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final s = await context.read<AppState>().store.screenings();
    if (mounted) setState(() => _screenings = s);
  }

  void _onSearch(String q) {
    setState(() {});
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 450), () async {
      if (q.trim().length < 2) {
        if (mounted) setState(() => _serverResults = null);
        return;
      }
      try {
        final res = await context.read<AppState>().api.searchPatients(q.trim());
        if (mounted) {
          setState(() {
            _serverResults = res;
            _searchInfo = null;
          });
        }
      } on OfflineException {
        if (mounted) setState(() => _searchInfo = 'Hors ligne : seuls les dépistages de ce téléphone sont affichés.');
      } catch (e) {
        if (mounted) setState(() => _searchInfo = '$e');
      }
    });
  }

  bool _matches(LocalRecord s) {
    final level = s.result?['risk_level'] as String?;
    final okFilter = switch (_filter) {
      'attente' => level == null,
      'tous' => true,
      _ => level == _filter,
    };
    final q = _search.text.trim().toLowerCase();
    return okFilter && (q.isEmpty || '${s.payload['patient_label'] ?? ''}'.toLowerCase().contains(q));
  }

  int _count(String key) => key == 'tous'
      ? _screenings.length
      : _screenings.where((s) => key == 'attente' ? (s.result?['risk_level'] == null) : (s.result?['risk_level'] == key)).length;

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final items = _screenings.where(_matches).toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mes dépistages'),
        actions: [
          IconButton(
            tooltip: 'Synchroniser',
            onPressed: app.syncing ? null : () => app.syncNow(silent: true),
            icon: app.syncing
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Badge(isLabelVisible: app.pendingCount > 0, label: Text('${app.pendingCount}'), child: const Icon(Icons.sync_rounded)),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(74),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 14),
            child: TextField(
              controller: _search,
              onChanged: _onSearch,
              decoration: InputDecoration(
                fillColor: Colors.white,
                prefixIcon: const Icon(Icons.search_rounded),
                hintText: 'Nom, code (CS-…) ou téléphone',
                contentPadding: const EdgeInsets.symmetric(vertical: 14),
                enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
                focusedBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
                suffixIcon: _search.text.isEmpty
                    ? null
                    : IconButton(icon: const Icon(Icons.close_rounded), onPressed: () {
                        _search.clear();
                        _onSearch('');
                      }),
              ),
            ),
          ),
        ),
      ),
      floatingActionButton: app.can('screenings:write') && app.forms.containsKey('sein')
          ? FloatingActionButton.extended(
              onPressed: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => const WizardScreen())),
              icon: const Icon(Icons.add_rounded),
              label: const Text('Nouveau', style: TextStyle(fontWeight: FontWeight.w700)),
            )
          : null,
      body: RefreshIndicator(
        onRefresh: () async => app.syncNow(silent: true),
        child: ListView(padding: const EdgeInsets.fromLTRB(16, 14, 16, 100), children: [
          // --- Filtres ---------------------------------------------------------------
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(children: [
              for (final (key, label) in _filters)
                Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text('$label  ${_count(key)}'),
                    selected: _filter == key,
                    showCheckmark: false,
                    selectedColor: key == 'tous' ? AppColors.primary : riskStyle(key == 'attente' ? null : key).$1,
                    labelStyle: TextStyle(color: _filter == key ? Colors.white : AppColors.ink, fontWeight: FontWeight.w700),
                    onSelected: (_) => setState(() => _filter = key),
                  ),
                ),
            ]),
          ),
          const SizedBox(height: 12),
          if (_searchInfo != null) Notice(text: _searchInfo!),

          // --- Résultats du serveur ----------------------------------------------------
          if (_serverResults != null) ...[
            const _Header('Dossiers sur le serveur'),
            if (_serverResults!.isEmpty) const Padding(padding: EdgeInsets.only(bottom: 12), child: Text('Aucun dossier trouvé.', style: TextStyle(color: AppColors.muted))),
            for (final p in _serverResults!)
              SoftCard(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                margin: const EdgeInsets.only(bottom: 10),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => PatientScreen.server(serverPatient: Map<String, dynamic>.from(p as Map)))),
                child: Row(children: [
                  const CircleAvatar(radius: 22, backgroundColor: Color(0xFFE3F0FD), child: Icon(Icons.cloud_rounded, color: AppColors.primary)),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text('${p['full_name'] ?? p['code']}', style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
                      Text('${p['code']} · ${p['locality'] ?? p['region']}', style: const TextStyle(color: AppColors.muted, fontSize: 13)),
                    ]),
                  ),
                  const Icon(Icons.chevron_right_rounded, color: AppColors.muted),
                ]),
              ),
          ],

          // --- Dépistages de l'appareil ---------------------------------------------------
          _Header(_serverResults != null ? 'Sur ce téléphone' : '${items.length} dépistage(s)'),
          if (items.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 40),
              child: Column(children: [
                Icon(Icons.inbox_rounded, size: 64, color: AppColors.muted.withValues(alpha: 0.5)),
                const SizedBox(height: 10),
                Text(_screenings.isEmpty ? 'Aucun dépistage sur ce téléphone.' : 'Aucun dépistage pour ce filtre.', style: const TextStyle(color: AppColors.muted)),
              ]),
            ),
          for (final s in items)
            SoftCard(
              padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
              margin: const EdgeInsets.only(bottom: 10),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ResultScreen(clientId: s.clientId))),
              child: Row(children: [
                Container(
                  width: 6,
                  height: 46,
                  decoration: BoxDecoration(color: riskStyle(s.result?['risk_level'] as String?).$1, borderRadius: BorderRadius.circular(4)),
                ),
                const SizedBox(width: 14),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('${s.payload['patient_label'] ?? 'Patiente'}', maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15.5)),
                    const SizedBox(height: 4),
                    Wrap(spacing: 10, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                      Text('${pathologyLabels[s.pathology] ?? ''} · ${formatDate(s.createdAt)}', style: const TextStyle(color: AppColors.muted, fontSize: 12.5)),
                      SyncStateChip(s.state),
                      if (s.alertCount > 0) AlertChip(text: '${s.alertCount} alerte${s.alertCount > 1 ? 's' : ''}'),
                    ]),
                  ]),
                ),
                const SizedBox(width: 8),
                RiskPill(s.result?['risk_level'] as String?, compact: true),
              ]),
            ),
        ]),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header(this.text);
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(4, 8, 4, 10),
        child: Text(text, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.muted)),
      );
}
