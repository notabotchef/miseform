'''Translation catalog, language resolution and locale number rendering.

Five cook languages ship with the toolchain: English (default), Spanish,
French, Italian and Portuguese. Only *rendered* text is localized: UI
labels, section headings, status lines and the decimal separator of rendered
numbers. The canonical card JSON stays locale-neutral (dot decimal, no
thousands grouping), so 1.000 and 1,000 are never interpreted ambiguously
and an amount is never changed by translation.

A language is resolved once per build run: CLI flag, then the card record's
``language`` field, then the host environment, then English. The resolved
language travels with the resolved theme into every edition -- Markdown,
HTML, PDF and XLSX -- so a card keeps one language from components through
assembly.
'''

from __future__ import annotations

import os
import re
import json
from pathlib import Path
from typing import Any

LANGUAGE_CODES = ("en", "es", "fr", "it", "pt")
DEFAULT_LANGUAGE = "en"

# Languages that render the decimal comma. Every other language renders the
# decimal dot. Never a thousands separator: amounts are printed exactly as
# the card states them, only the decimal mark changes.
_DECIMAL_COMMA_LANGUAGES = ("es", "fr", "it", "pt")

# Environment variables consulted for auto-detection, in order. The first
# usable value wins; the cook's explicit preference always overrides it.
_ENV_LANGUAGE_VARS = ("MISEFORM_LANGUAGE", "LC_ALL", "LANG")

# Every user-facing string the toolchain renders, per language. Message ids
# are stable; keys are the two-letter language codes above. A string with
# {braces} is formatted at render time and the placeholders are never
# translated.
MESSAGES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------- brand
    "brand.line": {
        "en": "The working recipe collection",
        "es": "La colección de recetas de trabajo",
        "fr": "La collection de recettes de travail",
        "it": "La raccolta di ricette di lavoro",
        "pt": "A coleção de receitas de trabalho",
    },
    "brand.default_library": {
        "en": "Working Recipe Collection",
        "es": "Colección de recetas de trabajo",
        "fr": "Collection de recettes de travail",
        "it": "Raccolta di ricette di lavoro",
        "pt": "Coleção de receitas de trabajo".replace("de trabajo", "de trabalho"),
    },
    # ------------------------------------------------------------- facts
    "facts.total_time": {
        "en": "Total time",
        "es": "Tiempo total",
        "fr": "Temps total",
        "it": "Tempo totale",
        "pt": "Tempo total",
    },
    "facts.difficulty": {
        "en": "Difficulty",
        "es": "Dificultad",
        "fr": "Difficulté",
        "it": "Difficoltà",
        "pt": "Dificuldade",
    },
    "facts.yield_portion": {
        "en": "Yield / portion",
        "es": "Rendimiento / porción",
        "fr": "Rendement / portion",
        "it": "Resa / porzione",
        "pt": "Rendimento / porção",
    },
    "facts.storage": {
        "en": "Storage",
        "es": "Almacenamiento",
        "fr": "Conservation",
        "it": "Conservazione",
        "pt": "Armazenamento",
    },
    # ----------------------------------------------------------- headings
    "heading.ingredients": {
        "en": "Ingredients",
        "es": "Ingredientes",
        "fr": "Ingrédients",
        "it": "Ingredienti",
        "pt": "Ingredientes",
    },
    "heading.method": {
        "en": "Method",
        "es": "Método",
        "fr": "Méthode",
        "it": "Metodo",
        "pt": "Método",
    },
    "heading.process_controls": {
        "en": "Process controls",
        "es": "Controles de proceso",
        "fr": "Contrôles de processus",
        "it": "Controlli di processo",
        "pt": "Controles de processo",
    },
    "heading.labeling": {
        "en": "Labeling",
        "es": "Etiquetado",
        "fr": "Étiquetage",
        "it": "Etichettatura",
        "pt": "Rotulagem",
    },
    "heading.notes": {
        "en": "Notes",
        "es": "Notas",
        "fr": "Notes",
        "it": "Note",
        "pt": "Notas",
    },
    "heading.release_before": {
        "en": "Required before production release",
        "es": "Requerido antes de la liberación para producción",
        "fr": "Requis avant la mise en production",
        "it": "Richiesto prima del rilascio in produzione",
        "pt": "Necessário antes do lançamento em produção",
    },
    "heading.release_record": {
        "en": "Release record",
        "es": "Registro de liberación",
        "fr": "Registre de mise en production",
        "it": "Registro di rilascio",
        "pt": "Registro de lançamento",
    },
    "heading.source_record": {
        "en": "Source and revision record",
        "es": "Fuente y registro de revisión",
        "fr": "Source et enregistrement de révision",
        "it": "Fonte e registro di revisione",
        "pt": "Fonte e registro de revisão",
    },
    # ------------------------------------------------------------- table
    "table.ingredient": {
        "en": "Ingredient",
        "es": "Ingrediente",
        "fr": "Ingrédient",
        "it": "Ingrediente",
        "pt": "Ingrediente",
    },
    "table.weight": {
        "en": "Weight",
        "es": "Peso",
        "fr": "Poids",
        "it": "Peso",
        "pt": "Peso",
    },
    "table.volume": {
        "en": "Volume",
        "es": "Volumen",
        "fr": "Volume",
        "it": "Volume",
        "pt": "Volume",
    },
    "table.scaling": {
        "en": "Scaling %",
        "es": "% de ajuste",
        "fr": "% d'ajustement",
        "it": "% di scalatura",
        "pt": "% de ajuste",
    },
    "table.yield_measured": {
        "en": "Measured usable yield",
        "es": "Rendimiento usable medido",
        "fr": "Rendement utilisable mesuré",
        "it": "Resa utilizzabile misurata",
        "pt": "Rendimento utilizável medido",
    },
    # ------------------------------------------------------------- caption
    "caption.basis": {
        "en": "Basis:",
        "es": "Base:",
        "fr": "Base :",
        "it": "Base:",
        "pt": "Base:",
    },
    "caption.input": {
        "en": "Input",
        "es": "Entrada",
        "fr": "Intrants",
        "it": "Input",
        "pt": "Entrada",
    },
    "caption.known_input_subtotal": {
        "en": "Known mass subtotal (partial)",
        "es": "Subtotal de masas conocidas (parcial)",
        "fr": "Sous-total des masses connues (partiel)",
        "it": "Subtotale delle masse note (parziale)",
        "pt": "Subtotal das massas conhecidas (parcial)",
    },
    "caption.unknown_input": {
        "en": "unknown",
        "es": "desconocida",
        "fr": "inconnus",
        "it": "sconosciuto",
        "pt": "desconhecida",
    },
    "caption.measured_output": {
        "en": "Measured usable output",
        "es": "Salida usable medida",
        "fr": "Rendement utilisable mesuré",
        "it": "Resa utilizzabile misurata",
        "pt": "Saída utilizável medida",
    },
    "caption.loss": {
        "en": "Transfer loss",
        "es": "Pérdida en el traslado",
        "fr": "Perte de transfert",
        "it": "Perdita di trasferimento",
        "pt": "Perda na transferência",
    },
    "caption.portions": {
        "en": "Complete portions",
        "es": "Porciones completas",
        "fr": "Portions complètes",
        "it": "Porzioni complete",
        "pt": "Porções completas",
    },
    "caption.remainder": {
        "en": "Remainder",
        "es": "Resto",
        "fr": "Reste",
        "it": "Resto",
        "pt": "Resto",
    },
    "caption.not_portioned": {
        "en": "not portioned.",
        "es": "sin racionar.",
        "fr": "non portioné.",
        "it": "non porzionato.",
        "pt": "não porcionado.",
    },
    "caption.no_volumes": {
        "en": "No ingredient volumes recorded; weigh ingredients.",
        "es": "No hay volúmenes de ingredientes registrados; pese los ingredientes.",
        "fr": "Aucun volume d'ingrédient enregistré ; pesez les ingrédients.",
        "it": "Nessun volume di ingrediente registrato; pesa gli ingredienti.",
        "pt": "Nenhum volume de ingrediente registrado; pese os ingredientes.",
    },
    "caption.volumes_researched": {
        "en": (
            "Volumes are researched approximations from cited sources, "
            "not measured spoonfuls; weigh ingredients."
        ),
        "es": (
            "Los volúmenes son aproximaciones investigadas de fuentes "
            "citadas, no cucharadas medidas; pese los ingredientes."
        ),
        "fr": (
            "Les volumes sont des approximations documentées, non des "
            "cuillères mesurées ; pesez les ingrédients."
        ),
        "it": (
            "I volumi sono approximazioni derivate da fonti citate, "
            "non cucchiai misurati; pesa gli ingredienti."
        ),
        "pt": (
            "Os volumes são aproximações pesquisadas de fontes citadas, "
            "não colheres medidas; pese os ingredientes."
        ),
    },
    "caption.volume_recorded": {
        "en": (
            "Volume recorded for {n} of {m} ingredients; a researched "
            "volume is an approximation, not a measured spoonful. "
            "Weigh ingredients."
        ),
        "es": (
            "Se registra volumen para {n} de {m} ingredientes; un "
            "volumen investigado es una aproximación, no una cucharada "
            "medida. Pese los ingredientes."
        ),
        "fr": (
            "Volume enregistré pour {n} des {m} ingrédients ; un volume "
            "documenté est une approximation, non une cuillère mesurée. "
            "Pesez les ingrédients."
        ),
        "it": (
            "Volume registrato per {n} di {m} ingredienti; un volume "
            "documentato è un'approssimazione, non un cucchiaio misurato. "
            "Pesa gli ingredienti."
        ),
        "pt": (
            "Volume registrado para {n} de {m} ingredientes; um volume "
            "pesquisado é uma aproximação, não uma colher medida. Pese os "
            "ingredientes."
        ),
    },
    # -------------------------------------------------------------- steps
    "settings.label": {
        "en": "Settings — ",
        "es": "Ajustes — ",
        "fr": "Réglages — ",
        "it": "Impostazioni — ",
        "pt": "Ajustes — ",
    },
    "tip.label": {
        "en": "Tip — ",
        "es": "Consejo — ",
        "fr": "Astuce — ",
        "it": "Suggerimento — ",
        "pt": "Dica — ",
    },
    # --------------------------------------------------------------- meta
    "meta.equipment": {
        "en": "Equipment / tested load:",
        "es": "Equipo / carga probada:",
        "fr": "Matériel / charge testée:",
        "it": "Attrezzatura / carico testato:",
        "pt": "Equipamento / carga testada:",
    },
    "meta.allergens": {
        "en": "Allergens:",
        "es": "Alérgenos:",
        "fr": "Allergènes:",
        "it": "Allergeni:",
        "pt": "Alergênicos:",
    },
    "meta.percentage_basis": {
        "en": "Percentage basis:",
        "es": "Base porcentual:",
        "fr": "Base de pourcentage:",
        "it": "Base percentuale:",
        "pt": "Base percentual:",
    },
    # ------------------------------------------------------------- status
    "status.release_warning": {
        "en": "NOT RELEASED FOR PRODUCTION",
        "es": "NO LIBERADO PARA PRODUCCIÓN",
        "fr": "NON LIBÉRÉ POUR LA PRODUCTION",
        "it": "NON RILASCIATO PER LA PRODUZIONE",
        "pt": "NÃO LIBERADO PARA PRODUÇÃO",
    },
    # ------------------------------------------------------------- trace
    "trace.evidence": {
        "en": "Evidence:",
        "es": "Evidencia:",
        "fr": "Preuves:",
        "it": "Evidenze:",
        "pt": "Evidências:",
    },
    "trace.validation": {
        "en": "Validation:",
        "es": "Validación:",
        "fr": "Validation:",
        "it": "Validazione:",
        "pt": "Validação:",
    },
    "trace.filing": {
        "en": 'Filing:',
        "es": 'Archivado:',
        "fr": 'Classement:',
        "it": 'Archiviazione:',
        "pt": 'Arquivamento:',
    },
    # ----------------------------------------------------------- labeling
    "labeling.product_name": {
        "en": 'Product name',
        "es": 'Nombre del producto',
        "fr": 'Nom du produit',
        "it": 'Nome del prodotto',
        "pt": 'Nome do produto',
    },
    "labeling.batch_or_date_code": {
        "en": 'Batch or date code',
        "es": 'Código de lote o fecha',
        "fr": 'Code de lot ou date',
        "it": 'Codice lotto o data',
        "pt": 'Código do lote ou data',
    },
    "labeling.use_by_basis": {
        "en": 'Use-by basis',
        "es": 'Base de fecha de consumo preferente',
        "fr": 'Base de la date limite de consommation',
        "it": 'Base per la scadenza',
        "pt": 'Base do prazo de validade',
    },
    "labeling.storage_instruction": {
        "en": 'Storage instruction',
        "es": 'Instrucción de almacenamiento',
        "fr": 'Instruction de conservation',
        "it": 'Istruzioni di conservazione',
        "pt": 'Instrução de armazenamento',
    },
    "labeling.allergen_declaration": {
        "en": 'Allergen declaration',
        "es": 'Declaración de alérgenos',
        "fr": 'Déclaration des allergènes',
        "it": 'Dichiarazione allergeni',
        "pt": 'Declaração de alergênicos',
    },
    "labeling.preparer_or_station": {
        "en": 'Preparer or station',
        "es": 'Preparador o estación',
        "fr": 'Préparateur ou poste',
        "it": 'Preparatore o stazione',
        "pt": 'Preparador ou estação',
    },
    # --------------------------------------------------------------- xlsx
    "xlsx.yield": {
        "en": "YIELD",
        "es": "RENDIMIENTO",
        "fr": "RENDEMENT",
        "it": "RESA",
        "pt": "RENDIMENTO",
    },
    "xlsx.time": {
        "en": "TIME {total} total ({active} active / {inactive} inactive)",
        "es": "TIEMPO {total} total ({active} activo / {inactive} inactivo)",
        "fr": "TEMPS {total} total ({active} actif / {inactive} inactif)",
        "it": "TEMPO {total} totale ({active} attivo / {inactive} inattivo)",
        "pt": "TEMPO {total} total ({active} ativo / {inactive} inativo)",
    },
    "xlsx.difficulty": {
        "en": "DIFFICULTY",
        "es": "DIFICULTAD",
        "fr": "DIFFICULTÉ",
        "it": "DIFFICOLTÀ",
        "pt": "DIFICULDADE",
    },
    "xlsx.storage": {
        "en": "STORAGE",
        "es": "ALMACENAMIENTO",
        "fr": "CONSERVATION",
        "it": "CONSERVAZIONE",
        "pt": "ARMAZENAMENTO",
    },
    "xlsx.equipment": {
        "en": "EQUIPMENT",
        "es": "EQUIPO",
        "fr": "MATÉRIEL",
        "it": "ATTREZZATURA",
        "pt": "EQUIPAMENTO",
    },
    "xlsx.allergens": {
        "en": "ALLERGENS",
        "es": "ALÉRGENOS",
        "fr": "ALLERGÈNES",
        "it": "ALLERGENI",
        "pt": "ALERGÊNIOS",
    },
    "xlsx.ingredients": {
        "en": "INGREDIENTS",
        "es": "INGREDIENTES",
        "fr": "INGRÉDIENTS",
        "it": "INGREDIENTI",
        "pt": "INGREDIENTES",
    },
    "xlsx.table.ingredient": {
        "en": "Ingredient",
        "es": "Ingrediente",
        "fr": "Ingrédient",
        "it": "Ingrediente",
        "pt": "Ingrediente",
    },
    "xlsx.table.weight": {
        "en": 'Weight (g)',
        "es": 'Peso (g)',
        "fr": 'Poids (g)',
        "it": 'Peso (g)',
        "pt": 'Peso (g)',
    },
    "xlsx.table.volume": {
        "en": 'Volume',
        "es": 'Volumen',
        "fr": 'Volume',
        "it": 'Volume',
        "pt": 'Volume',
    },
    "xlsx.table.scaling": {
        "en": 'Scaling %',
        "es": '% de ajuste',
        "fr": "% d'ajustement",
        "it": '% di scalatura',
        "pt": '% de ajuste',
    },
    "xlsx.table.base": {
        "en": 'Base (g)',
        "es": 'Base (g)',
        "fr": 'Base (g)',
        "it": 'Base (g)',
        "pt": 'Base (g)',
    },
    "xlsx.table.scaled": {
        "en": 'Scaled (g)',
        "es": 'Ajustado (g)',
        "fr": 'Ajusté (g)',
        "it": 'Scalato (g)',
        "pt": 'Ajustado (g)',
    },
    "xlsx.total_input": {
        "en": 'Total input',
        "es": 'Entrada total',
        "fr": 'Total des intrants',
        "it": 'Input totale',
        "pt": 'Entrada total',
    },
    "xlsx.total_input_g": {
        "en": 'Total input (g)',
        "es": 'Entrada total (g)',
        "fr": 'Total des intrants (g)',
        "it": 'Input totale (g)',
        "pt": 'Entrada total (g)',
    },
    "xlsx.input_total_mismatch": {
        "en": (
            "Declared input total {declared} does not equal the sum of the "
            "established ingredient weights {sum}."
        ),
        "es": (
            "El total de entrada declarado {declared} no coincide con la suma "
            "de las masas de ingredientes establecidas {sum}."
        ),
        "fr": (
            "Le total des intrants déclaré {declared} ne correspond pas à la "
            "somme des masses d'ingrédients établies {sum}."
        ),
        "it": (
            "L'input totale dichiarato {declared} non coincide con la somma "
            "delle masse di ingredienti stabilite {sum}."
        ),
        "pt": (
            "O total de entrada declarado {declared} não coincide com a soma "
            "das massas de ingredientes estabelecidas {sum}."
        ),
    },

    "xlsx.caption_note": {
        "en": (
            "Basis: {basis} Input total {input}. Volume not measured is "
            "shown as —; weigh ingredients."
        ),
        "es": (
            "Base: {basis} Entrada total {input}. El volumen no medido se "
            "muestra como —; pese los ingredientes."
        ),
        "fr": (
            "Base : {basis} Total des intrants {input}. Le volume non "
            "mesuré s'affiche comme — ; pesez les ingrédients."
        ),
        "it": (
            "Base: {basis} Input totale {input}. Il volume non misurato "
            "viene mostrato come —; pesa gli ingredienti."
        ),
        "pt": (
            "Base: {basis} Entrada total {input}. O volume não medido é "
            "mostrado como —; pese os ingredientes."
        ),
    },
    "xlsx.yield_g": {
        "en": "Measured usable yield (g)",
        "es": "Rendimiento usable medido (g)",
        "fr": "Rendement utilisable mesuré (g)",
        "it": "Resa utilizzabile misurata (g)",
        "pt": "Saída utilizável medida (g)",
    },
    "xlsx.loss_g": {
        "en": "Loss (g)",
        "es": "Pérdida (g)",
        "fr": "Perte (g)",
        "it": "Perdita (g)",
        "pt": "Perda (g)",
    },
    "xlsx.portion_g": {
        "en": "Portion weight (g)",
        "es": "Peso de la porción (g)",
        "fr": "Poids de la portion (g)",
        "it": "Peso della porzione (g)",
        "pt": "Peso da porção (g)",
    },
    "xlsx.complete_portions": {
        "en": "Complete portions",
        "es": "Porciones completas",
        "fr": "Portions complètes",
        "it": "Porzioni complete",
        "pt": "Porções completas",
    },
    "xlsx.process_controls": {
        "en": "PROCESS CONTROLS",
        "es": "CONTROLES DE PROCESO",
        "fr": "CONTRÔLES DE PROCESSUS",
        "it": "CONTROLLI DI PROCESSO",
        "pt": "CONTROLES DE PROCESSO",
    },
    "xlsx.labeling": {
        "en": "LABELING",
        "es": "ETIQUETADO",
        "fr": "ÉTIQUETAGE",
        "it": "ETICHETTATURA",
        "pt": "ROTULAGEM",
    },
    "xlsx.source_record": {
        "en": "SOURCE & REVISION RECORD",
        "es": "FUENTE & REGISTRO DE REVISIÓN",
        "fr": "SOURCE & ENREGISTREMENT DE RÉVISION",
        "it": "FONTE & REGISTRO DI REVISIONE",
        "pt": "FONTE & REGISTRO DE REVISÃO",
    },
    "xlsx.batch_scaling": {
        "en": "Batch scaling",
        "es": "Ajuste de lote",
        "fr": "Ajuste de lot",
        "it": "Scalatura del lotto",
        "pt": "Ajuste do lote",
    },
    "xlsx.batch_multiplier": {
        "en": "Batch multiplier · edit amber cell",
        "es": "Multiplicador de lote · editar celda ámbar",
        "fr": "Multiplicateur de lot · modifier la cellule ambrée",
        "it": "Moltiplicatore del lotto · modifica cella ambra",
        "pt": "Multiplicador do lote · editar célula âmbar",
    },
    "xlsx.batch_note": {
        "en": (
            "Enter a positive number. Ingredient weights are calculated; "
            "process, capacity and yield still require trial validation."
        ),
        "es": (
            "Introduzca un número positivo. Los pesos de los ingredientes "
            "se calculan; el proceso, la capacidad y el rendimiento aún "
            "requieren validación en prueba."
        ),
        "fr": (
            "Entrez un nombre positif. Les poids des ingrédients sont "
            "calculés ; le processus, la capacité et le rendement "
            "nécessitent encore une validation en essai."
        ),
        "it": (
            "Inserisci un numero positivo. I pesi degli ingredienti sono "
            "calcolati; processo, capacità e resa richiedono ancora "
            "validazione di prova."
        ),
        "pt": (
            "Insira um número positivo. Os pesos dos ingredientes são "
            "calculados; o processo, a capacidade e o rendimento ainda "
            "exigem validação em teste."
        ),
    },
    "xlsx.process_limits": {
        "en": "PROCESS LIMITS",
        "es": "LÍMITES DE PROCESO",
        "fr": "LIMITES DU PROCESSUS",
        "it": "LIMITI DI PROCESSO",
        "pt": "LIMITES DO PROCESSO",
    },
    "xlsx.tested_batch_range": {
        "en": "Tested batch range:",
        "es": "Rango de lote probado:",
        "fr": "Gamme de lots testée:",
        "it": "Gamma di lotti testata:",
        "pt": "Faixa de lote testada:",
    },
    "xlsx.limits_body": {
        "en": (
            "Scale ingredient amounts only. Do not scale time, temperature, "
            "vessel loading, mixing, cooling or fermentation automatically. "
            "Repeating a tested batch is different from increasing its load."
        ),
        "es": (
            "Ajuste solo las cantidades de los ingredientes. No escale "
            "automáticamente tiempo, temperatura, carga del vaso, mezclado, "
            "enfriamiento o fermentación. Repetir un lote probado no es lo "
            "mismo que aumentar su carga."
        ),
        "fr": (
            "Adaptez uniquement les quantités des ingrédients. N'adaptez pas "
            "automatiquement le temps, la température, le chargement du "
            "récipient, le mélange, le refroidissement ou la fermentation. "
            "Répéter un lot testé est différent d'en augmenter la charge."
        ),
        "it": (
            "Scalare solo le quantità degli ingredienti. Non scalare "
            "automaticamente tempo, temperatura, carico del recipiente, "
            "miscelatura, raffreddamento o fermentazione. Ripetere un lotto "
            "testato non è come aumentarne il carico."
        ),
        "pt": (
            "Ajuste apenas as quantidades dos ingredientes. Não ajuste "
            "automaticamente tempo, temperatura, carga do recipiente, "
            "mistura, resfriamento ou fermentação. Repetir um lote testado "
            "é diferente de aumentar sua carga."
        ),
    },
    "xlsx.yield_note": {
        "en": (
            "Finished yield must be weighed for every batch. Reference "
            "yield and portions below remain fixed to the original trial; "
            "scaled output is a projection, not a measured yield."
        ),
        "es": (
            "El rendimiento terminado debe pesarse en cada lote. El "
            "rendimiento y las porciones de referencia se mantienen fijos "
            "al ensayo original; el resultado ajustado es una proyección, "
            "no un rendimiento medido."
        ),
        "fr": (
            "Le rendement fini doit être pesé à chaque lot. Le rendement "
            "et les portions de référence restent fixés à l'essai original; "
            "le résultat ajusté est une projection, non un rendement mesuré."
        ),
        "it": (
            "La resa finita deve essere pesata per ogni lotto. La resa e "
            "le porzioni di riferimento restano fissate alla prova "
            "originale; l'output scalato è una proiezione, non una resa "
            "misurata."
        ),
        "pt": (
            "O rendimento final deve ser pesado a cada lote. O rendimento "
            "e as porções de referência permanecem fixos ao teste original; "
            "o resultado ajustado é uma projeção, não um rendimento medido."
        ),
    },
    "xlsx.ref_yield": {
        "en": "Reference usable yield (g)",
        "es": "Rendimiento usable de referencia (g)",
        "fr": "Rendement utilisable de référence (g)",
        "it": "Resa utilizzabile di riferimento (g)",
        "pt": "Saída utilizável de referência (g)",
    },
    "xlsx.ref_portion": {
        "en": "Reference portion weight (g)",
        "es": "Peso de la porción de referencia (g)",
        "fr": "Poids de la portion de référence (g)",
        "it": "Peso della porzione di riferimento (g)",
        "pt": "Peso da porção de referência (g)",
    },
    "xlsx.ref_portions": {
        "en": "Reference complete portions",
        "es": "Porciones completas de referencia",
        "fr": "Portions complètes de référence",
        "it": "Porzioni complete di riferimento",
        "pt": "Porções completas de referência",
    },
    "xlsx.source_quantities": {
        "en": (
            "Source quantities: Recipe Card. Amber cell is editable. Blank, "
            "zero, negative and text multipliers produce “Invalid input”."
        ),
        "es": (
            "Cantidades de origen: Tarjeta. La celda ámbar es editable. Los "
            "multiplicadores en blanco, cero, negativos o de texto producen "
            "“Invalid input”."
        ),
        "fr": (
            "Quantités de la source : Carte. La cellule ambrée est "
            "modifiable. Les multiplicateurs vides, nuls, négatifs ou en "
            "texte produisent “Invalid input”."
        ),
        "it": (
            "Quantità di origine: Scheda. La cella ambra è modificabile. "
            "I moltiplicatori vuoti, zero, negativi o di testo producono "
            "“Invalid input”."
        ),
        "pt": (
            "Quantidades de origem: Ficha. A célula âmbar é editável. "
            "Multiplicadores em branco, zero, negativos ou de texto "
            "produzem “Invalid input”."
        ),
    },
    "xlsx.rd_warning": {
        "en": (
            "R&D — NOT RELEASED FOR PRODUCTION. Scaling never grants "
            "production approval."
        ),
        "es": (
            "I+D — NO LIBERADO PARA PRODUCCIÓN. El ajuste nunca otorga "
            "aprobación de producción."
        ),
        "fr": (
            "R&D — NON LIBÉRÉ POUR LA PRODUCTION. L'ajustement ne vaut "
            "jamais approbation de production."
        ),
        "it": (
            "R&S — NON RILASCIATO PER LA PRODUZIONE. La scalatura non "
            "vale mai approvazione per la produzione."
        ),
        "pt": (
            "P&D — NÃO LIBERADO PARA PRODUÇÃO. O ajuste nunca vale "
            "aprovação de produção."
        ),
    },
    "xlsx.production_warning": {
        "en": "Scaling never grants production approval.",
        "es": "El ajuste nunca otorga aprobación de producción.",
        "fr": "L'ajustement ne vaut jamais approbation de production.",
        "it": "La scalatura non vale mai approvazione per la produzione.",
        "pt": "O ajuste nunca vale aprovação de produção.",
    },
    "xlsx.validation.error": {
        "en": "Enter a positive number.",
        "es": "Introduzca un número positivo.",
        "fr": "Entrez un nombre positif.",
        "it": "Inserisci un numero positivo.",
        "pt": "Insira um número positivo.",
    },
    "xlsx.validation.title": {
        "en": "Invalid input",
        "es": "Entrada no válida",
        "fr": "Entrée invalide",
        "it": "Input non valido",
        "pt": "Entrada inválida",
    },
    "xlsx.validation.prompt": {
        "en": 'Positive multiplier for ingredient weights only.',
        "es": 'Multiplicador positivo solo para los pesos de los ingredientes.',
        "fr": 'Multiplicateur positif pour les poids des ingrédients seulement.',
        "it": 'Moltiplicatore positivo solo per i pesi degli ingredienti.',
        "pt": 'Multiplicador positivo apenas para os pesos dos ingredientes.',
    },
    "xlsx.batch_factor": {
        "en": 'Batch factor',
        "es": 'Factor de lote',
        "fr": 'Facteur de lot',
        "it": 'Fattore del lotto',
        "pt": 'Fator do lote',
    },
    "xlsx.ambiguous_input": {
        "en": "Ambiguous component allocations; input total unknown",
        "es": "Asignaciones de componentes ambiguas; entrada total desconocida",
        "fr": "Allocations de composants ambiguës ; total des intrants inconnu",
        "it": "Allocazioni dei componenti ambigue; input totale sconosciuto",
        "pt": "Alocações de componentes ambíguas; entrada total desconhecida",
    },
    "xlsx.partial_input": {
        "en": 'Partial - {n} of {m} ingredient masses established; input total incomplete',
        "es": 'Parcial - {n} de {m} masas de ingredientes establecidas; el total de entrada está incompleto',
        "fr": 'Partiel - {n} sur {m} masses d\'ingrédients établies ; le total des intrants est incomplet',
        "it": 'Parziale - {n} di {m} masse di ingredienti stabilite; l\'input totale è incompleto',
        "pt": 'Parcial - {n} de {m} massas de ingredientes estabelecidas; o total de entrada está incompleto',
    },
    "xlsx.partial_scaling": {
        "en": 'Partial - {n} of {m} ingredient masses established; scaling total incomplete',
        "es": 'Parcial - {n} de {m} masas de ingredientes establecidas; el total de ajuste está incompleto',
        "fr": 'Partiel - {n} sur {m} masses d\'ingrédients établies ; le total d\'ajustement est incomplet',
        "it": 'Parziale - {n} di {m} masse di ingredienti stabilite; il totale di scalatura è incompleto',
        "pt": 'Parcial - {n} de {m} massas de ingredientes estabelecidas; o total de ajuste está incompleto',
    },
    "xlsx.no_input": {
        "en": 'No ingredient masses established; input total incomplete',
        "es": 'No se establecieron masas de ingredientes; el total de entrada está incompleto',
        "fr": 'Aucune masse d\'ingrédient établie ; le total des intrants est incomplet',
        "it": 'Nessuna massa di ingrediente stabilita; l\'input totale è incompleto',
        "pt": 'Nenhuma massa de ingrediente estabelecida; o total de entrada está incompleto',
    },
    "xlsx.no_scaling": {
        "en": 'No ingredient masses established; scaling total incomplete',
        "es": 'No se establecieron masas de ingredientes; el total de ajuste está incompleto',
        "fr": 'Aucune masse d\'ingrédient établie ; le total d\'ajustement est incomplet',
        "it": 'Nessuna massa di ingrediente stabilita; il totale di scalatura è incompleto',
        "pt": 'Nenhuma massa de ingrediente estabelecida; o total de ajuste está incompleto',
    },
    # --------------------------------------------------------------- cli
    "cli.card": {
        "en": "Card:",
        "es": "Ficha:",
        "fr": "Fiche:",
        "it": "Scheda:",
        "pt": "Ficha:",
    },
    "cli.findings": {
        "en": "Findings:",
        "es": "Hallazgos:",
        "fr": "Constatations:",
        "it": "Riscontri:",
        "pt": "Conclusões:",
    },
    "cli.findings_none": {
        "en": "Findings: none",
        "es": "Hallazgos: ninguno",
        "fr": "Constatations: aucune",
        "it": "Riscontri: nessuno",
        "pt": "Conclusões: nenhuma",
    },
    "cli.findings_count": {
        "en": "Findings: {n} ({b} blocker, {w} warning)",
        "es": "Hallazgos: {n} ({b} bloqueador, {w} aviso)",
        "fr": "Constatations: {n} ({b} bloquant, {w} avertissement)",
        "it": "Riscontri: {n} ({b} blocco, {w} avviso)",
        "pt": "Conclusões: {n} ({b} bloqueador, {w} aviso)",
    },
    "cli.theme": {
        "en": "theme:",
        "es": "tema:",
        "fr": "thème:",
        "it": "tema:",
        "pt": "tema:",
    },
    "cli.language": {
        "en": "language:",
        "es": "idioma:",
        "fr": "langue:",
        "it": "lingua:",
        "pt": "idioma:",
    },
    "cli.master": {
        "en": "master:",
        "es": "maestro:",
        "fr": "maître:",
        "it": "principale:",
        "pt": "mestre:",
    },
    "cli.pending": {
        "en": "PENDING",
        "es": "PENDIENTE",
        "fr": "EN ATTENTE",
        "it": "IN SOSPESO",
        "pt": "PENDENTE",
    },
    "cli.warning": {
        "en": "warning:",
        "es": "advertencia:",
        "fr": "avertissement:",
        "it": "avviso:",
        "pt": "aviso:",
    },
    "cli.required_pending": {
        "en": 'Required exports pending: {n}',
        "es": 'Exportaciones pendientes: {n}',
        "fr": 'Exportations en attente: {n}',
        "it": 'Esportazioni in sospeso: {n}',
        "pt": 'Exportações pendentes: {n}',
    },
    "cli.status": {
        "en": 'STATUS',
        "es": 'ESTADO',
        "fr": 'STATUT',
        "it": 'STATO',
        "pt": 'STATUS',
    },
    "cli.id_version": {
        "en": 'ID / VERSION',
        "es": 'ID / VERSIÓN',
        "fr": 'ID / VERSION',
        "it": 'ID / VERSIONE',
        "pt": 'ID / VERSÃO',
    },
    "cli.recipe_type": {
        "en": 'RECIPE TYPE',
        "es": 'TIPO DE RECETA',
        "fr": 'TYPE DE RECETTE',
        "it": 'TIPO DI RICETTA',
        "pt": 'TIPO DE RECEITA',
    },
    "cli.release_blockers": {
        "en": 'RELEASE BLOCKERS',
        "es": 'BLOQUEOS DE LIBERACIÓN',
        "fr": 'BLOCS DE MISE EN PRODUCTION',
        "it": 'BLOCCHI DI RILASCIO',
        "pt": 'BLOQUEIOS DE LANÇAMENTO',
    },
    "heading.directions": {
        "en": 'GENERAL DIRECTIONS',
        "es": 'INSTRUCCIONES GENERALES',
        "fr": 'DIRECTIONS GÉNÉRALES',
        "it": 'ISTRUZIONI GENERALI',
        "pt": 'INSTRUÇÕES GERAIS',
    },
    "totals.input": {
        "en": 'Input total',
        "es": 'Entrada total',
        "fr": 'Total des intrants',
        "it": 'Totale input',
        "pt": 'Total de entrada',
    },
    "totals.loss": {
        "en": 'Loss',
        "es": 'Pérdida',
        "fr": 'Perte',
        "it": 'Perdita',
        "pt": 'Perda',
    },
    "totals.portions": {
        "en": 'Complete portions',
        "es": 'Porciones completas',
        "fr": 'Portions complètes',
        "it": 'Porzioni complete',
        "pt": 'Porções completas',
    },
    "cli.blockers": {
        "en": (
            "Card has {n} blocking finding(s); it is not deliverable as a "
            "clean card."
        ),
        "es": (
            "La tarjeta tiene {n} hallazgo(s) bloqueante(s); no es "
            "entregable como una tarjeta limpia."
        ),
        "fr": (
            "La carte comporte {n} constatation(s) bloquante(s); elle n'est "
            "pas livrable en l'état."
        ),
        "it": (
            "La scheda presenta {n} riscontro/i bloccante/i; non è "
            "consegnabile come scheda pulita."
        ),
        "pt": (
            "A ficha tem {n} constatação(ões) bloqueadora(es); não é "
            "entregável como uma ficha limpa."
        ),
    },
    "cli.card_error": {
        "en": "CARD ERROR:",
        "es": "ERROR DE TARJETA:",
        "fr": "ERREUR CARTE:",
        "it": "ERRORE SCHEDA:",
        "pt": "ERRO DE FICHA:",
    },
}

# Proper product names and source text are never translated. These are kept
# verbatim in every language: branded items, origins and source citations.
UNTRANSLATED = frozenset({
    "tahini", "maldon", "hickory", "grapeseed", "japanese eggplant",
    "usda", "fooddata central", "king arthur",
})


MESSAGES.update({
    "status.partial_input": dict(zip(LANGUAGE_CODES, (
        "Partial input mass; quantities remain unresolved.",
        "Masa de entrada parcial; quedan cantidades sin resolver.",
        "Masse entrante partielle ; des quantités restent à résoudre.",
        "Massa iniziale parziale; alcune quantità restano da definire.",
        "Massa inicial parcial; há quantidades por resolver."))),
    "meta.status": dict(zip(LANGUAGE_CODES, ("Status", "Estado", "Statut", "Stato", "Estado"))),
    "meta.identity": dict(zip(LANGUAGE_CODES, ("ID / version", "ID / versión", "ID / version", "ID / versione", "ID / versão"))),
    "meta.recipe_type": dict(zip(LANGUAGE_CODES, ("Recipe type", "Tipo de receta", "Type de recette", "Tipo di ricetta", "Tipo de receita"))),
    "control.sous_vide": dict(zip(LANGUAGE_CODES, ("Sous vide", "Al vacío", "Sous vide", "Sottovuoto", "Sous vide"))),
    "control.combi": dict(zip(LANGUAGE_CODES, ("Combi oven", "Horno combinado", "Four mixte", "Forno combinato", "Forno combinado"))),
    "control.fermentation": dict(zip(LANGUAGE_CODES, ("Fermentation", "Fermentación", "Fermentation", "Fermentazione", "Fermentação"))),
    "control.pickling": dict(zip(LANGUAGE_CODES, ("Pickling", "Encurtido", "Marinage au vinaigre", "Sottaceto", "Conserva em vinagre"))),
    "control.reduction": dict(zip(LANGUAGE_CODES, ("Reduction", "Reducción", "Réduction", "Riduzione", "Redução"))),
    "control.emulsification": dict(zip(LANGUAGE_CODES, ("Emulsification", "Emulsificación", "Émulsification", "Emulsificazione", "Emulsificação"))),
    "control.chilling": dict(zip(LANGUAGE_CODES, ("Chilling", "Enfriamiento", "Refroidissement", "Raffreddamento", "Resfriamento"))),
    "control.smoking": dict(zip(LANGUAGE_CODES, ("Smoking", "Ahumado", "Fumage", "Affumicatura", "Defumação"))),
})


def translate(message_id: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Return the localized text for ``message_id`` in ``language``.

    A message missing for the requested language falls back to English; a
    message missing everywhere is returned as-is, so a render never
    invents text and never crashes on a gap. Catalog gaps are caught by
    tests, not by cooks in the kitchen.
    """
    table = MESSAGES.get(message_id)
    if not isinstance(table, dict):
        return message_id
    text = table.get(language)
    if text:
        return text
    text = table.get(DEFAULT_LANGUAGE)
    if text:
        return text
    return message_id


def normalize_language(value: Any) -> str | None:
    """Return a supported language code for ``value``, or None.

    Accepts ``es_ES``, ``es-ES``, ``es_ES.UTF-8`` and plain ``es``. Anything
    else (including an unsupported code) resolves to None.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    code = re.split(r"[_.-]", text, 1)[0].lower()
    return code if code in LANGUAGE_CODES else None


def detect_language() -> str | None:
    """Auto-detect the cook language from the host environment.

    Checked in order: MISEFORM_LANGUAGE, LC_ALL, LANG. The first usable
    supported code wins; None when nothing usable is set.
    """
    for var in _ENV_LANGUAGE_VARS:
        code = normalize_language(os.environ.get(var))
        if code is not None:
            return code
    return None


def resolve_language(cli_language: str | None, card_data: dict[str, Any]) -> str:
    """Resolve the language for one build run.

    CLI flag wins, then the card record's ``language`` field, then the host
    environment, then English. An absent or unsupported card field falls
    through to the next source, exactly like the theme field.
    """
    if cli_language is not None:
        code = normalize_language(cli_language)
        if code is not None:
            return code
    card_language = normalize_language(card_data.get("language"))
    if card_language is not None:
        return card_language
    detected = detect_language()
    if detected is not None:
        return detected
    return DEFAULT_LANGUAGE


def localize_decimals(text: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Render the decimal mark of a number in the language's convention.

    Only a digit-dot-digit sequence becomes digit-comma-digit, so a version
    like ``v0.1``, a URL and a dotted identifier are never touched. No
    thousands separator is ever added: ``1000`` stays ``1000``, never
    ``1.000`` or ``1,000``, and the amount is never changed.
    """
    if language not in _DECIMAL_COMMA_LANGUAGES:
        return text
    # Only a digit-dot-digit sequence becomes digit-comma-digit. A letter or
    # digit immediately before the first digit (a version like v0.1, a dotted
    # identifier inside a URL) blocks the match, so versions, URLs and dotted
    # identifiers are never touched. No thousands separator is ever added.
    return re.sub(r"(?<![A-Za-z])(\d+)\.(\d+)", r"\1,\2", text)


def format_number(value: float, language: str = DEFAULT_LANGUAGE) -> str:
    """Format a number with the language's decimal mark, no grouping."""
    if abs(value - round(value)) < 1e-9:
        text = f"{int(round(value))}"
    else:
        text = f"{value:.1f}"
    return localize_decimals(text, language)


from translation import FACTS, recipe_field


def recipe_text(texts: dict[str, Any] | None, key: str, default: str) -> str:
    """Return the translated recipe text for ``key``, or the card default.

    A translation bundle may override any scalar recipe field; fields it does
    not cover fall back to the card record, so a partial bundle is safe.
    """
    path = ('facts.' + key if key in FACTS else
            'percentage_basis.basis_label' if key == 'percentage_basis' else
            'stages.' + key[6:] if key.startswith('stage.') else key)
    return recipe_field(texts, path, default)


def note_text(texts: dict[str, Any] | None, index: int,
              default_heading: str, default_text: str) -> tuple[str, str]:
    """Return the translated heading and text for one note block."""
    if texts and 'schema_version' in texts:
        return (recipe_field(texts, f"notes.{index}.heading", default_heading),
                recipe_field(texts, f"notes.{index}.text", default_text))
    if not texts:
        return default_heading, default_text
    notes = texts.get("notes", []) or []
    if 0 <= index < len(notes):
        note = notes[index]
        heading = note.get("heading", default_heading)
        text = note.get("text", default_text)
        if not isinstance(heading, str):
            heading = default_heading
        if not isinstance(text, str):
            text = default_text
        return heading, text
    return default_heading, default_text


def component_name(texts: dict[str, Any] | None, default: str) -> str:
    """Return the translated name for one component, or the card default."""
    if not texts:
        return default
    name = texts.get("component")
    if isinstance(name, str) and name.strip():
        return name
    return default


def ingredient_name(texts: dict[str, Any] | None, row_id: str,
                    default: str) -> str:
    """Return the translated name for one ingredient row, or the card default.

    The lookup is keyed by the canonical row_id so a translated generic name
    never replaces the row id the procedure references; proper product names
    stay verbatim and are never translated.
    """
    if not texts:
        return default
    for comp in texts.get("components", []) or []:
        for ing in comp.get("ingredients", []) or []:
            if str(ing.get("row_id", "")) == row_id:
                name = ing.get("name")
                if isinstance(name, str) and name.strip():
                    return name
                break
    return default


def step_text(texts: dict[str, Any] | None, stage_index: int, step_number: int,
              default: str) -> str:
    """Return the translated text for one step, or the card default."""
    if texts and 'schema_version' in texts:
        return recipe_field(texts, f"stages.{stage_index}.steps.{step_number}.text", default)
    if not texts:
        return default
    stages = texts.get("stages", []) or []
    if 0 <= stage_index < len(stages):
        for step in stages[stage_index].get("steps", []) or []:
            if step.get("number") == step_number:
                text = step.get("text")
                if isinstance(text, str) and text.strip():
                    return text
                break
    return default


def load_translation_bundle(
    language: str, card_path: Path | str
) -> dict[str, Any] | None:
    """Load the persisted per-language translation bundle for one card.

    A translation bundle is a synthetic JSON fixture that overrides rendered
    recipe text (title, intro, allergens, ingredient names, step texts,
    notes) for one language. Fields the bundle does not cover fall back to
    the card record, so a partial bundle is safe.

    Search order:
      1. <card_stem>.lang-<code>.json next to the card file.
      2. examples/translations/<card_stem>.lang-<code>.json relative to the
         repository root (two levels up from this file).

    Returns None when no bundle exists, so a build with no bundle still
    renders every edition directly from the card record.
    """
    if language == DEFAULT_LANGUAGE:
        return None
    card = Path(card_path)
    stem = card.stem
    candidates = [
        card.with_name(f"{stem}.lang-{language}.json"),
        card.resolve().parent.parent / "examples" / "translations"
        / f"{stem}.lang-{language}.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"translation sidecar {candidate} exists but is not valid "
                    f"JSON: {exc}"
                ) from exc
            if not isinstance(data, dict):
                raise ValueError(
                    f"translation sidecar {candidate} must contain a JSON "
                    f"object, got {type(data).__name__}"
                )
            return data
    return None


__all__ = [
    "LANGUAGE_CODES",
    "DEFAULT_LANGUAGE",
    "MESSAGES",
    "translate",
    "normalize_language",
    "detect_language",
    "resolve_language",
    "localize_decimals",
    "format_number",
    "recipe_text",
    "note_text",
    "component_name",
    "ingredient_name",
    "step_text",
    "load_translation_bundle",
]
