import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../core/app_state.dart';
import '../core/form_logic.dart';
import '../theme.dart';
import '../widgets/form_renderer.dart';
import '../widgets/ui.dart';
import 'result_screen.dart';

/// Nouveau dépistage en plusieurs étapes (une étape par section du formulaire).
/// Pour une nouvelle patiente, l'identification est saisie à la première étape.
/// Tout est enregistré sur l'appareil puis synchronisé : fonctionne hors connexion.
class WizardScreen extends StatefulWidget {
  const WizardScreen({super.key, this.pathology = 'sein', this.patientClientId, this.serverPatientId, this.patientLabel});

  final String pathology;
  /// Patiente existante : créée sur l'appareil…
  final String? patientClientId;
  /// …ou connue du serveur.
  final String? serverPatientId;
  final String? patientLabel;

  bool get isNewPatient => patientClientId == null && serverPatientId == null;

  @override
  State<WizardScreen> createState() => _WizardScreenState();
}

class _WizardScreenState extends State<WizardScreen> {
  int _step = 0;
  final Map<String, Object?> _data = {};
  final Map<String, String> _errors = {};
  bool _busy = false;

  // Identification (nouvelle patiente)
  bool _consent = false;
  bool _consentResearch = false;
  final _age = TextEditingController();
  final _locality = TextEditingController();
  final _name = TextEditingController();
  final _phone = TextEditingController();
  String _region = 'Maritime';

  FormDef get _form => context.read<AppState>().forms[widget.pathology]!;
  bool get _isLast => _step == _form.sections.length - 1;

  int? get _ageValue {
    final n = int.tryParse(_age.text.trim());
    return (n != null && n >= 10 && n <= 110) ? n : null;
  }

  /// Contrôle de l'étape courante avant de passer à la suivante.
  bool _validateStep() {
    final errors = <String, String>{};
    if (_step == 0 && widget.isNewPatient) {
      if (!_consent) errors['_consent'] = 'Le consentement éclairé est obligatoire';
      if (_ageValue == null) errors['_age'] = 'Indiquez un âge entre 10 et 110 ans (estimé si besoin)';
    }
    final section = _form.sections[_step];
    final check = checkForm(_form, _data);
    for (final f in section.fields) {
      if (check.missing.contains(f.id)) errors[f.id] = 'Réponse obligatoire (choisissez NSP si la patiente ne sait pas)';
      if (check.errors.containsKey(f.id)) errors[f.id] = check.errors[f.id]!;
    }
    setState(() {
      _errors
        ..clear()
        ..addAll(errors);
    });
    if (errors.isNotEmpty) showError(context, 'Complétez les champs signalés en rouge.');
    return errors.isEmpty;
  }

  void _go(int delta) {
    if (delta > 0 && !_validateStep()) return;
    setState(() {
      _step += delta;
      _errors.clear();
    });
  }

  Future<bool> _confirmLeave() async {
    if (_data.isEmpty && _age.text.isEmpty) return true;
    return await showDialog<bool>(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text('Abandonner le dépistage ?'),
            content: const Text('Les réponses saisies seront perdues.'),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Continuer')),
              TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Abandonner')),
            ],
          ),
        ) ??
        false;
  }

  Future<void> _analyse() async {
    if (!_validateStep()) return;
    setState(() => _busy = true);
    final app = context.read<AppState>();
    String? patientClientId = widget.patientClientId;
    var label = widget.patientLabel ?? 'Patiente';
    if (widget.isNewPatient) {
      final now = DateTime.now();
      final patient = await app.createPatient({
        'full_name': _name.text.trim().isEmpty ? null : _name.text.trim(),
        'phone': _phone.text.trim().isEmpty ? null : _phone.text.trim(),
        'birth_date': null,
        'birth_year_estimated': now.year - _ageValue!,
        'region': _region,
        'locality': _locality.text.trim().isEmpty ? null : _locality.text.trim(),
        'consent_given': true,
        'consent_date': now.toIso8601String().substring(0, 10),
        'consent_research': _consentResearch,
      });
      patientClientId = patient.clientId;
      label = _name.text.trim().isNotEmpty ? _name.text.trim() : '${_ageValue!} ans — ${_locality.text.trim().isEmpty ? _region : _locality.text.trim()}';
    }
    final record = await app.createScreening(
      form: _form,
      data: _data,
      patientClientId: patientClientId,
      serverPatientId: widget.serverPatientId,
      patientLabel: label,
    );
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => ResultScreen(clientId: record.clientId)));
  }

  @override
  Widget build(BuildContext context) {
    final form = _form;
    final section = form.sections[_step];
    final total = form.sections.length;

    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        if (_step > 0) {
          _go(-1);
        } else if (await _confirmLeave() && context.mounted) {
          Navigator.of(context).pop();
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: Text(form.pathology == 'sein' ? 'Nouveau dépistage' : 'Dépistage — ${pathologyLabels[form.pathology] ?? ''}'),
          bottom: PreferredSize(
            preferredSize: const Size.fromHeight(78),
            child: _Stepper(labels: [for (var i = 0; i < total; i++) stepLabel(form.sections[i].id, i)], current: _step),
          ),
        ),
        body: AnimatedSwitcher(
          duration: const Duration(milliseconds: 260),
          transitionBuilder: (child, anim) => FadeTransition(
            opacity: anim,
            child: SlideTransition(position: Tween(begin: const Offset(0.06, 0), end: Offset.zero).animate(anim), child: child),
          ),
          child: ListView(
            key: ValueKey(_step),
            padding: const EdgeInsets.fromLTRB(16, 18, 16, 28),
            children: [
              _SectionHeader(icon: sectionIcon(section.icon), subtitle: 'Étape ${_step + 1} sur $total', title: section.title),
              if (_step == 0 && !form.validated)
                Notice(kind: NoticeKind.warning, text: 'Formulaire provisoire (v${form.version}) : à valider par des professionnels de santé.'),
              if (_step == 0 && widget.isNewPatient) _FieldsCard(title: 'Identification', icon: Icons.badge_rounded, child: _identification()),
              if (_step == 0 && !widget.isNewPatient) Notice(text: 'Patiente : ${widget.patientLabel ?? ''}'),
              if (_isLast) _recap(form),
              _FieldsCard(
                title: _step == 0 ? 'Antécédents' : (_isLast ? 'Votre appréciation' : null),
                icon: _step == 0 ? Icons.family_restroom_rounded : (_isLast ? Icons.psychology_alt_rounded : null),
                child: SectionFields(section: section, data: _data, errors: _errors, onChanged: (id, v) => setState(() => v == null ? _data.remove(id) : _data[id] = v)),
              ),
              if (_isLast)
                const Notice(text: 'Appuyez sur « Analyser » pour enregistrer le dépistage et obtenir l\'analyse IA du risque. '
                    'Sans connexion, l\'analyse sera faite automatiquement à la synchronisation.'),
            ],
          ),
        ),
        bottomNavigationBar: SafeArea(
          child: Container(
            decoration: const BoxDecoration(
              color: Colors.white,
              boxShadow: [BoxShadow(color: Color(0x14000000), blurRadius: 16, offset: Offset(0, -4))],
            ),
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 12),
            child: Row(children: [
              if (_step > 0) ...[
                Expanded(child: OutlinedButton.icon(onPressed: _busy ? null : () => _go(-1), icon: const Icon(Icons.arrow_back), label: const Text('Précédent'))),
                const SizedBox(width: 16),
              ],
              Expanded(
                child: _isLast
                    ? FilledButton.icon(onPressed: _busy ? null : _analyse, icon: const Icon(Icons.check), label: Text(_busy ? 'Enregistrement…' : 'Analyser'))
                    : FilledButton.icon(onPressed: () => _go(1), icon: const Icon(Icons.arrow_forward), label: const Text('Suivant')),
              ),
            ]),
          ),
        ),
      ),
    );
  }

  Widget _identification() {
    final year = DateTime.now().year;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Container(
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: _errors.containsKey('_consent') ? AppColors.alert : const Color(0xFFD5DEE8), width: 1.5),
        ),
        child: Column(children: [
          SwitchListTile(
            value: _consent,
            onChanged: (v) => setState(() => _consent = v),
            title: const Text('Consentement éclairé de la patiente *', style: TextStyle(fontWeight: FontWeight.w600)),
            subtitle: const Text('Recueil de ses données pour le dépistage'),
          ),
          const Divider(height: 1),
          SwitchListTile(
            value: _consentResearch,
            onChanged: (v) => setState(() => _consentResearch = v),
            title: const Text('Accepte l\'usage pour la recherche'),
            subtitle: const Text('Facultatif — données pseudonymisées'),
          ),
        ]),
      ),
      if (_errors['_consent'] != null) _err(_errors['_consent']!),
      const SizedBox(height: 14),
      TextField(
        enabled: false,
        decoration: const InputDecoration(labelText: 'Code patient (anonyme)', hintText: 'Attribué automatiquement à la synchronisation'),
      ),
      const SizedBox(height: 14),
      TextField(
        controller: _age,
        keyboardType: TextInputType.number,
        decoration: InputDecoration(
          labelText: 'Âge *',
          suffixText: 'ans',
          helperText: _ageValue == null ? 'Estimé si la date de naissance est inconnue' : 'Née vers ${year - _ageValue!}',
          errorText: _errors['_age'],
        ),
        onChanged: (_) => setState(() {}),
      ),
      const SizedBox(height: 14),
      TextField(controller: _locality, decoration: const InputDecoration(labelText: 'Localité')),
      const SizedBox(height: 14),
      DropdownButtonFormField<String>(
        initialValue: _region,
        decoration: const InputDecoration(labelText: 'Région'),
        items: [for (final r in togoRegions) DropdownMenuItem(value: r, child: Text(r))],
        onChanged: (v) => setState(() => _region = v!),
      ),
      const SizedBox(height: 6),
      Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: const Text('Coordonnées pour le suivi (facultatif)', style: TextStyle(color: AppColors.primary, fontWeight: FontWeight.w600)),
          subtitle: const Text('Chiffrées sur l\'appareil, jamais transmises au moteur IA'),
          children: [
            TextField(controller: _name, textCapitalization: TextCapitalization.words, decoration: const InputDecoration(labelText: 'Nom complet')),
            const SizedBox(height: 12),
            TextField(controller: _phone, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'Téléphone', hintText: '+228 90 00 00 00')),
            const SizedBox(height: 8),
          ],
        ),
      ),
    ]);
  }

  /// Récapitulatif avant l'analyse (dernière étape).
  Widget _recap(FormDef form) {
    final check = checkForm(form, _data);
    String v(String id) {
      final f = form.field(id);
      return f == null ? '—' : displayValue(f, _data[id]);
    }

    final rows = <(String, String)>[
      if (widget.isNewPatient) ...[
        ('Âge', _ageValue != null ? '$_ageValue ans' : '—'),
        ('Localité', _locality.text.trim().isEmpty ? _region : '${_locality.text.trim()} ($_region)'),
      ] else
        ('Patiente', widget.patientLabel ?? '—'),
      ('Antécédent familial sein / ovaire', v('atcd_familial_sein_ovaire')),
      ('Cancer du sein antérieur', v('atcd_personnel_sein')),
      ('Masse perçue', v('masse_presente')),
      ('Modification de la peau', v('modif_peau')),
      ('Mamelon rentré', v('retraction_mamelon')),
      ('Consistance de la masse', v('masse_consistance')),
      ('Mobilité de la masse', v('masse_mobilite')),
    ];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          const Text('Récapitulatif du dépistage', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
          const Divider(height: 24),
          for (final (label, value) in rows)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: Row(children: [
                Expanded(child: Text(label, style: const TextStyle(color: Colors.black54, fontSize: 15))),
                Text(value, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
              ]),
            ),
          if (check.alerts.isNotEmpty) ...[
            const Divider(height: 24),
            Text('${check.alerts.length} signe(s) d\'alerte : ${check.alerts.map((f) => f.label).join(' · ')}',
                style: const TextStyle(color: AppColors.alert, fontWeight: FontWeight.w700)),
          ],
        ]),
      ),
    );
  }

  Widget _err(String text) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Text(text, style: const TextStyle(color: AppColors.alert, fontWeight: FontWeight.w600, fontSize: 13)),
      );
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.icon, required this.subtitle, required this.title});
  final IconData icon;
  final String subtitle;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 0, 4, 16),
      child: Row(children: [
        Container(
          width: 54,
          height: 54,
          decoration: BoxDecoration(gradient: AppColors.brandGradient, borderRadius: BorderRadius.circular(16), boxShadow: const [
            BoxShadow(color: Color(0x402196F3), blurRadius: 12, offset: Offset(0, 5)),
          ]),
          child: Icon(icon, color: Colors.white, size: 28),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(subtitle.toUpperCase(), style: const TextStyle(color: AppColors.primary, fontSize: 12, fontWeight: FontWeight.w800, letterSpacing: 0.8)),
            const SizedBox(height: 2),
            Text(title, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          ]),
        ),
      ]),
    );
  }
}

/// Étapes numérotées : terminées (coche), en cours (blanche), à venir (transparentes).
class _Stepper extends StatelessWidget {
  const _Stepper({required this.labels, required this.current});
  final List<String> labels;
  final int current;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 14),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        for (var i = 0; i < labels.length; i++) ...[
          Expanded(
            child: Column(children: [
              AnimatedContainer(
                duration: const Duration(milliseconds: 250),
                width: 32,
                height: 32,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: i <= current ? Colors.white : Colors.white.withValues(alpha: 0.18),
                  border: Border.all(color: Colors.white.withValues(alpha: i <= current ? 1 : 0.5), width: 1.5),
                ),
                child: Center(
                  child: i < current
                      ? const Icon(Icons.check_rounded, size: 19, color: AppColors.primaryDark)
                      : Text('${i + 1}', style: TextStyle(color: i == current ? AppColors.primaryDark : Colors.white, fontWeight: FontWeight.w800)),
                ),
              ),
              const SizedBox(height: 6),
              Text(labels[i],
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(color: i == current ? Colors.white : Colors.white70, fontSize: 11.5, fontWeight: i == current ? FontWeight.w800 : FontWeight.w500)),
            ]),
          ),
          if (i < labels.length - 1)
            Container(
              width: 14,
              height: 2,
              margin: const EdgeInsets.only(top: 15),
              color: Colors.white.withValues(alpha: i < current ? 0.9 : 0.35),
            ),
        ],
      ]),
    );
  }
}

/// Carte blanche qui regroupe les questions d'une étape.
class _FieldsCard extends StatelessWidget {
  const _FieldsCard({required this.child, this.title, this.icon});
  final Widget child;
  final String? title;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return SoftCard(
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        if (title != null) ...[
          Row(children: [
            if (icon != null) ...[Icon(icon, color: AppColors.primary, size: 22), const SizedBox(width: 10)],
            Text(title!, style: const TextStyle(color: AppColors.primary, fontSize: 16, fontWeight: FontWeight.w800)),
          ]),
          const SizedBox(height: 16),
        ],
        child,
      ]),
    );
  }
}
