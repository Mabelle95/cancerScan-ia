import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/api_client.dart';
import '../core/app_state.dart';
import '../core/local_store.dart';
import '../widgets/ui.dart';
import 'result_screen.dart';
import 'wizard_screen.dart';

/// Dossier d'une patiente : créée sur l'appareil, ou trouvée sur le serveur.
class PatientScreen extends StatefulWidget {
  const PatientScreen.local({super.key, required LocalRecord this.localPatient}) : serverPatient = null;
  const PatientScreen.server({super.key, required Map<String, dynamic> this.serverPatient}) : localPatient = null;

  final LocalRecord? localPatient;
  final Map<String, dynamic>? serverPatient;

  @override
  State<PatientScreen> createState() => _PatientScreenState();
}

class _PatientScreenState extends State<PatientScreen> {
  List<LocalRecord> _local = [];
  List<dynamic>? _remote;
  String? _remoteError;

  String get _label =>
      (widget.localPatient?.payload['full_name'] ?? widget.serverPatient?['full_name'] ?? widget.serverPatient?['code'] ?? 'Patiente') as String;

  String? get _serverId => widget.serverPatient?['id'] as String? ?? widget.localPatient?.serverId;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final app = context.read<AppState>();
    final local = widget.localPatient != null
        ? await app.store.screeningsOfLocalPatient(widget.localPatient!.clientId)
        : await app.store.screeningsOfServerPatient(_serverId!);
    if (mounted) setState(() => _local = local);
    if (_serverId == null) return;
    try {
      final remote = await app.api.patientScreenings(_serverId!);
      if (mounted) setState(() => _remote = remote);
    } on OfflineException {
      if (mounted) setState(() => _remoteError = 'Historique du serveur indisponible hors ligne.');
    } catch (e) {
      if (mounted) setState(() => _remoteError = '$e');
    }
  }

  Future<void> _newScreening() async {
    final p = widget.localPatient;
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => WizardScreen(
        // Patiente locale non encore synchronisée : le dépistage partira avec elle
        patientClientId: p != null && p.serverId == null ? p.clientId : null,
        serverPatientId: p != null && p.serverId == null ? null : _serverId,
        patientLabel: _label,
      ),
    ));
    _load();
  }

  @override
  Widget build(BuildContext context) {
    final app = context.watch<AppState>();
    final localServerIds = _local.map((s) => s.serverId).whereType<String>().toSet();
    final remoteOnly = (_remote ?? []).where((s) => !localServerIds.contains(s['id'])).toList();
    final p = widget.localPatient;

    return Scaffold(
      appBar: AppBar(title: Text(_label)),
      floatingActionButton: app.can('screenings:write')
          ? FloatingActionButton.extended(onPressed: _newScreening, icon: const Icon(Icons.add), label: const Text('Nouveau dépistage'))
          : null,
      body: ListView(padding: const EdgeInsets.fromLTRB(16, 12, 16, 96), children: [
        if (p != null)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                SyncStateChip(p.state),
                if (p.error != null) Padding(padding: const EdgeInsets.only(top: 8), child: Notice(kind: NoticeKind.danger, text: p.error!)),
                const SizedBox(height: 8),
                Text('Téléphone : ${p.payload['phone'] ?? '—'}'),
                Text('Naissance : ${p.payload['birth_date'] ?? (p.payload['birth_year_estimated'] != null ? '~${p.payload['birth_year_estimated']}' : '—')}'),
                Text('Localité : ${[p.payload['locality'], p.payload['region']].whereType<String>().join(', ')}'),
              ]),
            ),
          ),
        if (widget.serverPatient?['code'] != null)
          Padding(padding: const EdgeInsets.only(bottom: 8), child: Text('Dossier ${widget.serverPatient!['code']}', style: Theme.of(context).textTheme.bodySmall)),
        Padding(
          padding: const EdgeInsets.fromLTRB(4, 12, 4, 8),
          child: Text('Dépistages', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700)),
        ),
        for (final s in _local)
          Card(
            child: ListTile(
              title: Text(pathologyLabels[s.pathology] ?? '${s.pathology}'),
              subtitle: Wrap(spacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: [
                Text(formatDate(s.createdAt)),
                SyncStateChip(s.state),
                if (s.alertCount > 0) const AlertChip(),
              ]),
              trailing: RiskBadge(s.result?['risk_level'] as String?),
              onTap: () => Navigator.of(context).push(MaterialPageRoute(builder: (_) => ResultScreen(clientId: s.clientId))),
            ),
          ),
        for (final s in remoteOnly)
          Card(
            child: ListTile(
              leading: const Icon(Icons.cloud_outlined),
              title: Text(pathologyLabels[s['pathology']] ?? '${s['pathology']}'),
              subtitle: Text('${s['submitted_at'] ?? s['created_at']}'.substring(0, 10)),
              trailing: RiskBadge((s['assessments'] as List).isEmpty ? null : s['assessments'][0]['risk_level'] as String?),
            ),
          ),
        if (_local.isEmpty && remoteOnly.isEmpty) const Padding(padding: EdgeInsets.all(16), child: Text('Aucun dépistage.')),
        if (_remoteError != null) Text(_remoteError!, style: Theme.of(context).textTheme.bodySmall),
      ]),
    );
  }
}
