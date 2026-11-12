# Revisão de conclusão sem retomar agentes

`review-completion` avalia registros existentes e cria uma saída separada. Não
inicia runtime, executor, modelos ou serviços externos, não renova conferência
financeira e não altera o estado operacional bruto, respostas, receipts ou
contadores do run. Os caminhos de saída devem ser novos; mantenha-os fora do
Store e das evidências originais.

Há duas formas de revisar. Sem `--review`, a política automática
`python-smoke-v1` continua restrita ao objetivo e aos hashes exatos da fixture
Python publicada. Para PHP/WordPress e outros inventários, forneça uma revisão
explícita do operador. Ela não depende de uma lista de hashes de fixtures.

## Revisão explícita

Gere um modelo vinculado ao relatório atual:

```bash
.venv/bin/audit3 --store /caminho/do/store review-completion ID --template --output /caminho/novo/modelo.json
```

A saída é um rascunho (`draft: true`), não uma aprovação. Código de saída 0 nessa
operação significa somente que o arquivo foi criado. O rascunho contém versão do
avaliador, objetivo original, hash do contexto, hash do inventário e mensagens
identificadas com critérios e referências. Não altere esses vínculos para fazer
uma revisão antiga parecer atual. Notas sem suporte suficiente não recebem
um candidato de classificação no rascunho e continuam pendentes na avaliação;
a ausência de uma entrada em `messages` não remove a ressalva original.

Revise o inventário, o objetivo, o julgamento e as evidências referenciadas. No
JSON, informe a identificação em `reviewer`, a justificativa geral em
`scope.rationale` e uma `justification` específica para cada mensagem que pretende
classificar. Preencha também, segundo o objetivo efetivo:

- `scope.production_occurrence_required`: se a conclusão depende de demonstrar
  ocorrência em produção.
- `scope.quantitative_measurement_required`: se a conclusão exige medição
  quantitativa de cobertura ou contagens que o receipt não fornece.
- `scope.secret_absence_certification_required`: se o objetivo exige certificar
  ausência de segredos/PII, além da inspeção e do scanner heurístico disponíveis.

Esses campos aceitam decisões explícitas do revisor. `null` permanece pendente;
`false` nunca é deduzido automaticamente do texto. Se uma dessas evidências é
necessária, marcar `true` impede dispensar a ressalva correspondente. O operador
é responsável pela interpretação fiel do objetivo: marcar `false` não produz
prova de produção, cobertura numérica ou ausência de segredos.

Avalie o rascunho preenchido:

```bash
.venv/bin/audit3 --store /caminho/do/store review-completion ID --review /caminho/novo/modelo.json --output /caminho/novo/avaliacao.json
```

O comando sela o rascunho com um ID por hash, sem atualizar seu objetivo, versão
ou contexto. A saída contém `review` e `completion_assessment`; o estado bruto
continua separado. Rascunho insuficiente continua `partial`. Uma revisão selada
precisa ter ID íntegro. O envelope retornado pode ser reavaliado diretamente:

```bash
.venv/bin/audit3 --store /caminho/do/store review-completion ID --review /caminho/novo/avaliacao.json --output /caminho/novo/reavaliacao.json
```

Para incluir a avaliação e as evidências publicadas em um ZIP novo e separado:

```bash
.venv/bin/audit3 --store /caminho/do/store review-completion ID --review /caminho/novo/avaliacao.json --output /caminho/novo/avaliacao-exportada.json --export /caminho/novo/avaliacao.zip
```

O ZIP preserva `state` bruto e inclui a conclusão revisada separadamente. A
exportação não sobrescreve os relatórios do Store e recusa destino dentro dele.
Uma avaliação parcial pode ser exportada como parcial, sem se tornar aprovada.

Código 0 na avaliação significa conclusão do escopo; 2 indica pendências ou erro.
Isso não substitui a aceitação específica de um smoke nem transforma um mock em
execução real. Se as evidências mudarem, a revisão anterior é recusada. Gere e
revise um novo rascunho; não copie o hash atual para dispensar a revisão.

## Critérios e bloqueios

A política `explicit-scope-v1` suporta três ressalvas do controlador, sempre
preservando seu texto e proveniência:

| Critério | Ressalva e evidência necessária |
|---|---|
| `inventory-reviewed` | Scanner heurístico: inventário e escopo íntegros e examinados, sem lacunas obrigatórias; objetivo não exige uma certificação de ausência que o scanner não demonstra. |
| `production-outside-objective` | Ausência de ocorrência em produção: objetivo explicitamente não exige demonstrar ocorrência; achados e julgamento mantêm esse limite. |
| `executor-measurement` | Exit code e contagens desconhecidas: nota originada no receipt do controlador, com execução válida e vinculada à mesma fonte/run; objetivo não exige as medidas ausentes. |

Uma frase igual emitida pelo modelo não adquire autoridade do Executor. Um
ponteiro existente, uma justificativa genérica ou correspondência textual não
bastam. A ressalva dos receipts permanece visível e contadores desconhecidos
continuam `null`; nenhuma estimativa de casos, cobertura, tokens ou custo é criada.

Ficam bloqueantes: investigação cega não demonstrada, fases ausentes, julgamento
inválido, evidência obrigatória não consultada, achados sem contraditório, fonte
alterada, isolamento incompatível, causalidade exigida sem prova, limites
excedidos, timeout, execução ausente, saída incompleta relevante e limitações
novas ou não esclarecidas. A revisão não remove esses controles.

Um baseline `passed` é compatível com a conclusão de uma auditoria de código
correto e sem achados. A exigência de baseline `failed` pertence à aceitação do
smoke que deve reproduzir um defeito conhecido, não à conclusão geral. Achados
PHP individuais com IDs separados e `root_cause_id` nulo ou exclusivo continuam
sem depender de certificados Python.

## Revisão explícita das narrativas dos papéis

O avaliador `scoped-assessment-5` também aceita `explicit-narrative-v1`, critério
`reviewed-claims`. Não há classificação automática de narrativas nem lista de
frases dispensáveis. A política automática Python permanece restrita à sua
fixture. Uma mensagem desconhecida continua pendente até ser examinada.

Use o mesmo rascunho e os mesmos comandos `review-completion` acima. Preserve o
cabeçalho `policy: explicit-scope-v1`, o revisor, os campos `scope`, o objetivo e
os vínculos atuais; acrescente `narrative_policy: explicit-narrative-v1`. Para
cada mensagem narrativa revisada, informe:

- `policy: explicit-narrative-v1`, `criterion: reviewed-claims`, o texto em
  `original_text`, seu `original_hash` e todas as `origins` atuais.
- `claims`: partes contíguas, com `start` inclusivo, `end` exclusivo e `text`
  exatamente iguais ao original. Todas as partes da mensagem devem ser
  examinadas. Cada parte tem `kind`, `requirement_ids`, `interpretation`,
  `semantic_responsibility: reviewer`, `checks` e `facts`.
- `requirements_hash`: hash de `narrative_requirements`, lista no cabeçalho que
  cobre integralmente o objetivo original com os mesmos campos de intervalo,
  mais `id` único e `interpretation`. Não substitua o objetivo por uma paráfrase.
- `evidence`: conjunto exato dos ponteiros de relatório usados nos fatos dessa
  mensagem e de seus limites de escopo. Os fatos de fonte/script têm suas
  próprias chaves autenticadas, descritas abaixo.

Cada afirmação exige as verificações `source_integrity`, `protocol`,
`final_judgment` e `receipt_integrity`. Há também `initial_investigation`,
`causal_separation` (IDs sem fusão) e `limits`, quando pertinentes. Os bloqueios
estruturais gerais são aplicados mesmo se não forem citados na afirmação.
Receipts ausentes, com timeout, truncamento, hashes incoerentes ou de outra
fonte/run não sustentam uma dispensa narrativa.

`facts` contém predicados verificáveis: `domain: report` com `reference` para
cobertura, verificações estruturais, receipts, inventário, fases concluídas,
veredictos ou comparações; ou `domain: source`/`test` com `key`. Os operadores
são `equals` (valor JSON exato), `hash` (SHA-256 do JSON canônico), `contains` e
`not_contains` (trecho literal não vazio). O valor esperado fica em `expected`.
Não use texto do modelo como fato independente. Um ponteiro existente ou uma
flag isolada não é suporte suficiente: deve haver fato de fonte, script ou
resultado primário de cobertura/execução/julgamento pertinente à afirmação.

O cabeçalho `evidence_bundle` tem `sources` (caminho → texto integral) e `tests`
(ID do receipt → script integral). O avaliador confere esses textos pelos
SHA-256 do inventário e dos receipts antes de usá-los. Ele não executa os textos.
Para `scope_note`, informe também `boundary_id`, apontando para uma entrada em
`scope_boundaries` com `requirement_ids`, `interpretation`,
`semantic_responsibility: reviewer` e `facts`. Esse limite explica por que a
informação ausente não integra o objetivo **original**, sem alterá-lo.

A máquina confere vínculos, abrangência textual, predicados e condições
estruturais. **O revisor assume a interpretação semântica**: a pertinência dos
fatos, a decomposição de afirmações misturadas, o alcance do contrato e a
resolução de aparentes contradições. Hashes e predicados não provam sozinhos
essa interpretação. Justificativa preenchida e rótulo escolhido não substituem
esse exame. Mensagem de modelo não vira nota do Executor; as políticas e
proveniências continuam distintas.

A classificação da mensagem agrega suas partes: `blocking` prevalece sobre
`unresolved`, que prevalece sobre `procedure_note` e `scope_note`. Não deixe uma
parte não examinada. Um fato ausente/contraditório ou uma revisão inválida mantém
a mensagem pendente; evidência modificada invalida o contexto da revisão.

Para reproduzir uma revisão já preenchida e versionada, sem executar agentes:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/audit3 --store .audit3 review-completion ID --review /caminho/revisao.json --output /caminho/novo/avaliacao.json --export /caminho/novo/avaliacao.zip
```

Essa saída ainda deixa a aceitação específica como `not_evaluated`. Uma
reavaliação de run histórico deve identificar separadamente o commit executado,
a versão do avaliador e o resultado derivado. Não a apresente como execução real
da implementação modificada. Os registros e a aceitação históricos permanecem
inalterados.

## Reprocessamento de uma resposta histórica selecionada

`scripts/reprocess_saved_response.py` continua disponível para avaliar uma
resposta final original, com certificados e uma revisão de conclusão explícitos.
Ele não escreve no Store original. A saída deve ser um diretório novo e separado
do Store e das evidências de entrada.

Os parâmetros são `--run`, `--invocation`, `--response`, `--certificates`,
`--completion-review`, `--known-path`, `--known-line` e `--output`; `--store` é
opcional. O JSON da resposta deve corresponder byte a byte ao checkpoint concluído.
O relatório derivado preserva `state` e apresenta a conclusão revisada em
`completion_assessment`. A revisão deve corresponder ao contexto da resposta
selecionada, não ao contexto de outra resposta do mesmo run.

Esse script também aplica a aceitação específica de processo e causa conhecida;
use `review-completion` para a revisão geral do escopo. A prova causal
`pure-expression-intervention-1` é restrita a expressões Python suportadas e
observações registradas. Ela não executa o programa auditado nem equivale a um
verificador genérico para PHP ou programas arbitrários.

Revisões e certificados são dados explícitos do operador, nunca autoridade
extraída de instruções do projeto auditado. Aprovação derivada offline não autoriza
retomada, não libera gastos e não substitui uma aceitação histórica. Roteiros
antigos de `validation/` permanecem evidências da versão anterior; não executá-los
para fabricar conformidade retroativa.
