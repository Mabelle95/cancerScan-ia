import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../core/form_logic.dart';
import '../theme.dart';

/// Champs d'une section du formulaire partagé (une étape de l'assistant).
class SectionFields extends StatelessWidget {
  const SectionFields({super.key, required this.section, required this.data, required this.onChanged, required this.errors});

  final FormSectionDef section;
  final Map<String, Object?> data;
  final void Function(String id, Object? value) onChanged;
  final Map<String, String> errors;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      for (final f in section.fields.where((f) => isVisible(f, data)))
        _FieldInput(key: ValueKey(f.id), field: f, value: data[f.id], error: errors[f.id], onChanged: (v) => onChanged(f.id, v)),
    ]);
  }
}

/// Titre de groupe bleu (« Antécédents familiaux », « Palpation »…).
class GroupTitle extends StatelessWidget {
  const GroupTitle(this.text, {super.key});
  final String text;
  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 18, bottom: 10),
        child: Text(text, style: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700, fontSize: 16)),
      );
}

class _FieldInput extends StatelessWidget {
  const _FieldInput({super.key, required this.field, required this.value, required this.onChanged, this.error});

  final FormFieldDef field;
  final Object? value;
  final String? error;
  final ValueChanged<Object?> onChanged;

  String get _label => '${field.label}${field.required ? ' *' : ''}';

  @override
  Widget build(BuildContext context) {
    final alert = isAlert(field, value);
    final Widget body = switch (field.type) {
      'boolean' => _booleanRow(context, alert),
      'choice' => _choice(context, alert),
      'multichoice' => _multi(context),
      'integer' || 'number' => _number(),
      _ => _text(),
    };
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        body,
        if (field.help != null)
          Padding(padding: const EdgeInsets.only(top: 4), child: Text(field.help!, style: const TextStyle(fontSize: 13, color: Colors.black54))),
        if (error != null)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(error!, style: const TextStyle(color: AppColors.alert, fontWeight: FontWeight.w600, fontSize: 13)),
          ),
      ]),
    );
  }

  /// Une ligne : la question à gauche, Oui / Non / NSP à droite (un seul toucher).
  Widget _booleanRow(BuildContext context, bool alert) {
    return Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
      Expanded(
        child: Text(_label,
            style: TextStyle(fontSize: 16, color: alert ? AppColors.alert : Colors.black87, fontWeight: alert ? FontWeight.w700 : FontWeight.w400)),
      ),
      const SizedBox(width: 8),
      _TriState(
        value: value,
        alertOnYes: field.hasAlertWhen && field.alertWhen == true,
        onChanged: onChanged,
      ),
    ]);
  }

  Widget _choice(BuildContext context, bool alert) {
    final short = field.options.length <= 3 && field.options.every((o) => o.label.length <= 14);
    if (short) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(_label, style: TextStyle(fontSize: 16, color: alert ? AppColors.alert : Colors.black87, fontWeight: alert ? FontWeight.w700 : FontWeight.w400)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final o in field.options)
            ChoiceChip(
              label: Text(o.label),
              selected: value == o.value,
              showCheckmark: false,
              selectedColor: o.alert ? AppColors.eleve : AppColors.primary,
              labelStyle: TextStyle(color: value == o.value ? Colors.white : null, fontWeight: FontWeight.w600),
              onSelected: (_) => onChanged(value == o.value ? null : o.value),
            ),
        ]),
      ]);
    }
    return DropdownButtonFormField<String>(
      initialValue: field.options.any((o) => o.value == value) ? value as String : null,
      isExpanded: true,
      decoration: InputDecoration(
        labelText: _label,
        labelStyle: TextStyle(color: alert ? AppColors.alert : null),
        enabledBorder: alert
            ? OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: const BorderSide(color: AppColors.alert, width: 2))
            : null,
      ),
      items: [
        const DropdownMenuItem<String>(value: null, child: Text('— Non renseigné —', style: TextStyle(color: Colors.black45))),
        for (final o in field.options)
          DropdownMenuItem(value: o.value, child: Text(o.label, style: TextStyle(color: o.alert ? AppColors.alert : null))),
      ],
      onChanged: onChanged,
    );
  }

  Widget _multi(BuildContext context) {
    final current = value is List ? List<Object?>.from(value as List) : <Object?>[];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(_label, style: const TextStyle(fontSize: 16)),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final o in field.options)
          FilterChip(
            label: Text(o.label),
            selected: current.contains(o.value),
            onSelected: (on) => onChanged(on ? [...current, o.value] : current.where((x) => x != o.value).toList()),
          ),
      ]),
    ]);
  }

  Widget _number() => TextFormField(
        initialValue: value is num ? _fmt(value as num) : '',
        keyboardType: TextInputType.numberWithOptions(decimal: field.type == 'number'),
        inputFormatters: [FilteringTextInputFormatter.allow(RegExp(field.type == 'number' ? r'[0-9.,]' : r'[0-9]'))],
        decoration: InputDecoration(
          labelText: _label,
          suffixText: field.unit,
          helperText: field.min != null && field.max != null ? 'De ${_fmt(field.min!)} à ${_fmt(field.max!)}' : null,
          errorText: error != null ? '' : null,
          errorStyle: const TextStyle(height: 0, fontSize: 0),
        ),
        onChanged: (t) {
          final n = num.tryParse(t.replaceAll(',', '.'));
          onChanged(n == null ? null : (field.type == 'integer' ? n.toInt() : n));
        },
      );

  Widget _text() => TextFormField(
        initialValue: value as String? ?? '',
        minLines: 3,
        maxLines: 6,
        maxLength: 5000,
        decoration: InputDecoration(labelText: _label, alignLabelWithHint: true),
        onChanged: (t) => onChanged(t.isEmpty ? null : t),
      );

  static String _fmt(num n) => n == n.roundToDouble() ? n.toInt().toString() : n.toString();
}

/// Sélecteur compact Oui / Non / NSP. NSP (« ne sait pas ») est enregistré comme « inconnu » :
/// une donnée manquante n'est jamais confondue avec un « non » (cahier des charges §7.3).
class _TriState extends StatelessWidget {
  const _TriState({required this.value, required this.onChanged, required this.alertOnYes});
  final Object? value;
  final bool alertOnYes;
  final ValueChanged<Object?> onChanged;

  @override
  Widget build(BuildContext context) {
    Widget seg(Object v, String text, Color color) {
      final on = value == v;
      return InkWell(
        onTap: () => onChanged(on ? null : v),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 150),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          color: on ? color : Colors.white,
          child: Text(text, style: TextStyle(color: on ? Colors.white : Colors.black87, fontWeight: on ? FontWeight.w700 : FontWeight.w500)),
        ),
      );
    }

    return Container(
      decoration: BoxDecoration(border: Border.all(color: const Color(0xFF9AA0A6)), borderRadius: BorderRadius.circular(22)),
      clipBehavior: Clip.antiAlias,
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        seg(true, 'Oui', alertOnYes ? AppColors.eleve : AppColors.primary),
        Container(width: 1, height: 38, color: const Color(0xFF9AA0A6)),
        seg(false, 'Non', AppColors.primary),
        Container(width: 1, height: 38, color: const Color(0xFF9AA0A6)),
        seg(unknownValue, 'NSP', AppColors.pending),
      ]),
    );
  }
}
