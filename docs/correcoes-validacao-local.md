# Correções e validação local do controlador

Esta revisão corrige a implementação e seus contratos locais. Mocks não validam
uma auditoria real; testes Docker só demonstram os cenários sintéticos executados.
Nenhuma correção exige novas confirmações financeiras para os testes locais.

## Investigação inicial

Auditor e Defensor precisam registrar inspeções que cubram seus lotes `initial-*`.
As referências são conferidas contra leituras autênticas do mesmo papel, run e
snapshot, na etapa inicial e antes da barreira. Correções e recuperação podem
reutilizar leituras iniciais legítimas. Leituras posteriores não completam a
cobertura cega. O Juiz precisa de inspeção própria dirigida em `blind`, incluindo
um requisito/invariante e referências; consultar só o baseline não basta. Um
parecer sem achados continua válido. Arquivos sem linhas são identificados sem
referências artificiais; um inventário totalmente sem linhas auditáveis bloqueia.

A barreira e fases persistidas são verificadas novamente. A avaliação separada
`coverage.independent_investigation` registra lacunas estruturais que uma revisão
narrativa não pode dispensar. Registros históricos permanecem inalterados; a
avaliação atual pode demonstrar insuficiência das evidências antigas.

## Estado bruto, revisão e aceitação

`state` continua sendo o resultado operacional bruto. As duas notas normais da
preparação podem produzir `partial`. Isso só é compatível com aceitação quando o
protocolo está concluído, todas as verificações estruturais passam e existe uma
revisão atual que justifique cada pendência restante.

O avaliador `scoped-assessment-3` vincula a revisão ao objetivo, inventário,
pareceres, julgamento, receipts, streams, consultas, barreira, comparações,
contabilidade e estado operacional. A revisão tem ID por hash, versão, contexto,
mensagens identificadas, critérios, justificativas e referências. Um ponteiro
válido para qualquer parte do relatório não basta. Mudanças nas evidências
invalidam a revisão; revisões antigas não são convertidas silenciosamente.

O critério empacotado `python-smoke-v1` aplica-se exclusivamente ao objetivo e aos
hashes da fixture `codex-smoke` publicados em `assets/smoke-review-policy.json`.
Ele permite classificar apenas as notas de preparação sobre scanner heurístico e
ausência de ocorrência em produção, verificando inventário integral, fonte
íntegra, baseline executado e julgamento final. Outras limitações permanecem
pendentes. Timeout, limites, falta de investigação, evidência, julgamento,
contraditório ou integridade não viram notas de escopo. Mock continua mock.

A validação futura do smoke prepara duas reproduções de estorno e controles
positivos com o recurso `assets/smoke-causality.py`, exclusivamente no executor
isolado. Os pareceres que usarem essa evidência precisam citar seu receipt e a
função completa. Certificados são verificados contra as referências e os casos
observados antes de fundir IDs; rótulos compartilhados não provam equivalência.
Esse procedimento é opt-in para a fixture Python. Um defeito PHP individual com
ID separado e `root_cause_id` nulo/exclusivo continua sem exigir certificado Python.

O JSON e Markdown apresentam estado bruto, conclusão derivada, revisão, bloqueios
e aceitação. `three-agents-acceptance.json` só é produzido após as verificações do
processo real e da causa conhecida; `results.json` consolida esses estados.

## Comandos reproduzíveis

Suíte local, sem modelos nem Docker:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -m 'not docker and not live'
```

Infraestrutura sintética, apenas com imagens já adquiridas e aprovadas:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 AUDIT3_LIVE_TEST=0 AUDIT3_WORDPRESS_TEST=1 .venv/bin/python -m pytest -q -m 'docker and not live' tests/test_executor.py tests/test_fixtures_integration.py
```

Avaliação offline separada de um run existente, sem modificar seus registros:

```bash
.venv/bin/audit3 --store /caminho/do/store review-completion ID --output /caminho/novo/avaliacao.json
```

O arquivo de saída deve ser novo e seu diretório deve existir. Código de saída 0
significa escopo concluído; 2 indica pendências ou erro. A avaliação não declara
que um mock seja real e não constitui, sozinha, aceitação do smoke.

Somente em uma tarefa futura explicitamente autorizada, com login dedicado,
franquia oficial observável e conferência financeira factual ainda válida conforme
`codex-pro.md`, o comando existente integra preparação causal, fluxo, revisão e
aceitação:

```bash
.venv/bin/python scripts/validate_pending.py --codex --financial-confirmation /caminho/privado/fatos.json
```

Esse comando inicia modelos reais e **não faz parte da validação local desta
correção**. Não repete automaticamente redações ou amplia limites para aprovar.
Qualquer nova limitação ou prova insuficiente mantém a aceitação pendente.

Aquisição Git, limites de blobs e limpeza de subprocessos estão detalhados em
`seguranca.md`; o guard de despacho e os estados `not_sent`/ambíguo estão em
`codex-pro.md`.
