// Logique des formulaires partagés (shared/forms), alignée sur api/app/services/forms.py
// et web/src/formLogic.ts. Le serveur reste la référence ; ce contrôle local permet de
// guider l'agent et de détecter les signes d'alerte même hors connexion.

const unknownValue = 'inconnu';

class FormOption {
  FormOption(this.value, this.label, this.alert);
  final String value;
  final String label;
  final bool alert;

  factory FormOption.fromJson(Map<String, dynamic> j) =>
      FormOption(j['value'] as String, j['label'] as String, j['alert'] == true);
}

class ShowIf {
  ShowIf(this.field, this.hasEquals, this.equals, this.greaterThan);
  final String field;
  final bool hasEquals;
  final Object? equals;
  final num? greaterThan;

  factory ShowIf.fromJson(Map<String, dynamic> j) =>
      ShowIf(j['field'] as String, j.containsKey('equals'), j['equals'], j['greater_than'] as num?);
}

class FormFieldDef {
  FormFieldDef({
    required this.id,
    required this.label,
    required this.type,
    this.required = false,
    this.min,
    this.max,
    this.unit,
    this.options = const [],
    this.hasAlertWhen = false,
    this.alertWhen,
    this.showIf,
    this.help,
    this.afterResult = false,
  });

  final String id;
  final String label;
  final String type; // boolean, integer, number, choice, multichoice, text, date
  final bool required;
  final num? min;
  final num? max;
  final String? unit;
  final List<FormOption> options;
  final bool hasAlertWhen;
  final Object? alertWhen;
  final ShowIf? showIf;
  final String? help;
  /// Question posée APRÈS le résultat de l'IA (ex. appréciation de l'agent) : cachée pendant la saisie.
  final bool afterResult;

  factory FormFieldDef.fromJson(Map<String, dynamic> j) => FormFieldDef(
        id: j['id'] as String,
        label: j['label'] as String,
        type: j['type'] as String,
        required: j['required'] == true,
        min: j['min'] as num?,
        max: j['max'] as num?,
        unit: j['unit'] as String?,
        options: [for (final o in (j['options'] as List? ?? [])) FormOption.fromJson(o as Map<String, dynamic>)],
        hasAlertWhen: j.containsKey('alert_when'),
        alertWhen: j['alert_when'],
        showIf: j['show_if'] == null ? null : ShowIf.fromJson(j['show_if'] as Map<String, dynamic>),
        help: j['help'] as String?,
        afterResult: j['after_result'] == true,
      );
}

class FormSectionDef {
  FormSectionDef(this.id, this.title, this.fields, {this.icon});
  final String id;
  final String title;
  final String? icon;
  final List<FormFieldDef> fields;

  factory FormSectionDef.fromJson(Map<String, dynamic> j) => FormSectionDef(
        j['id'] as String,
        j['title'] as String,
        [for (final f in j['fields'] as List) FormFieldDef.fromJson(f as Map<String, dynamic>)],
        icon: j['icon'] as String?,
      );
}

class FormDef {
  FormDef(this.pathology, this.title, this.version, this.validated, this.sections);
  final String pathology;
  final String title;
  final String version;
  final bool validated;
  final List<FormSectionDef> sections;

  Iterable<FormFieldDef> get fields => sections.expand((s) => s.fields);
  FormFieldDef? field(String id) => fields.where((f) => f.id == id).firstOrNull;

  factory FormDef.fromJson(Map<String, dynamic> j) => FormDef(
        j['pathology'] as String,
        j['title'] as String,
        j['version'] as String,
        j['validated'] == true,
        [for (final s in j['sections'] as List) FormSectionDef.fromJson(s as Map<String, dynamic>)],
      );
}

bool isMissing(Object? v) => v == null || v == '' || (v is List && v.isEmpty);

bool isVisible(FormFieldDef f, Map<String, Object?> data) {
  final cond = f.showIf;
  if (cond == null) return true;
  final other = data[cond.field];
  if (cond.hasEquals) return other == cond.equals;
  if (cond.greaterThan != null) return other is num && other > cond.greaterThan!;
  return true;
}

String? fieldError(FormFieldDef f, Object? v) {
  if (isMissing(v)) return null;
  switch (f.type) {
    case 'boolean':
      return (v == true || v == false || v == unknownValue) ? null : 'Valeur attendue : oui, non ou inconnu';
    case 'integer':
    case 'number':
      if (v is! num) return 'Valeur numérique attendue';
      if (f.type == 'integer' && v != v.roundToDouble()) return 'Nombre entier attendu';
      if (f.min != null && v < f.min!) return 'Minimum : ${_fmt(f.min!)}';
      if (f.max != null && v > f.max!) return 'Maximum : ${_fmt(f.max!)}';
      return null;
    case 'choice':
      return f.options.any((o) => o.value == v) ? null : 'Option non reconnue';
    case 'multichoice':
      return (v is List && v.every((x) => f.options.any((o) => o.value == x))) ? null : 'Options non reconnues';
    default:
      return null;
  }
}

String _fmt(num n) => n == n.roundToDouble() ? n.toInt().toString() : n.toString();

bool isAlert(FormFieldDef f, Object? v) {
  if (isMissing(v)) return false;
  if (f.hasAlertWhen && v == f.alertWhen) return true;
  final values = v is List ? v : [v];
  return f.options.any((o) => o.alert && values.contains(o.value));
}

class FormCheck {
  final List<String> missing = [];
  final Map<String, String> errors = {};
  final List<FormFieldDef> alerts = [];
  final Map<String, Object?> cleaned = {};

  bool get isComplete => missing.isEmpty && errors.isEmpty;
}

/// Valide une saisie : champs masqués ignorés (et non envoyés), obligatoires manquants, erreurs, alertes.
FormCheck checkForm(FormDef form, Map<String, Object?> data) {
  final result = FormCheck();
  for (final f in form.fields) {
    if (!isVisible(f, data)) continue;
    final v = data[f.id];
    if (isMissing(v)) {
      if (f.required) result.missing.add(f.id);
      continue;
    }
    final err = fieldError(f, v);
    if (err != null) {
      result.errors[f.id] = err;
      continue;
    }
    result.cleaned[f.id] = v;
    if (isAlert(f, v)) result.alerts.add(f);
  }
  return result;
}

String displayValue(FormFieldDef f, Object? v) {
  if (isMissing(v)) return '—';
  if (f.type == 'boolean') return v == true ? 'Oui' : v == false ? 'Non' : 'Inconnu';
  String label(Object? x) => f.options.where((o) => o.value == x).firstOrNull?.label ?? '$x';
  if (v is List) return v.map(label).join(', ');
  if (f.options.isNotEmpty) return label(v);
  return f.unit != null ? '$v ${f.unit}' : '$v';
}
