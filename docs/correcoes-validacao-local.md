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

O avaliador `scoped-assessment-4` vincula a revisão ao objetivo, inventário,
pareceres, julgamento, receipts, streams, consultas, barreira, comparações,
contabilidade e estado operacional. A revisão tem ID por hash, versão, contexto,
mensagens identificadas, critérios, justificativas e referências. Um ponteiro
válido para qualquer parte do relatório não basta. Mudanças nas evidências
invalidam a revisão; revisões antigas não são convertidas silenciosamente.

O critério automático empacotado `python-smoke-v1` continua restrito ao objetivo
e aos hashes da fixture `codex-smoke` publicados em
`assets/smoke-review-policy.json`. Ele pode classificar as notas de preparação
sobre scanner heurístico e ausência de ocorrência em produção, além da ressalva
normal do Executor sobre exit code e contagens desconhecidas. A classificação
confere inventário, origem das mensagens e evidências; não remove seu texto e
não converte contadores desconhecidos em zero. Uma frase igual em um parecer do
modelo não recebe a autoridade de uma nota do controlador.

A revisão explícita `explicit-scope-v1` oferece critérios para PHP/WordPress e
outros inventários, sem cadastrar hashes de uma segunda fixture. O revisor
identifica-se, interpreta o objetivo em campos estruturados, justifica cada nota
e confirma o inventário/contexto atual. Se o objetivo exigir uma informação que
a nota declara ausente, a dispensa continua bloqueada. Um baseline aprovado é
compatível com a conclusão geral de código correto, inclusive sem achados; a
falha esperada do baseline continua exigida pelo contrato específico do smoke.

Timeout, isolamento incompatível, limites excedidos, falta de investigação,
evidência, julgamento, contraditório ou integridade permanecem bloqueantes.
Limitações desconhecidas não são classificadas automaticamente. Mock continua
mock. O [procedimento de revisão explícita](reprocessamento-local.md) descreve os
campos, critérios e comandos que preservam o estado bruto e os registros originais.

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

Para outros objetivos, gere um rascunho, preencha-o após examinar as evidências e
valide-o em outro arquivo novo:

```bash
.venv/bin/audit3 --store /caminho/do/store review-completion ID --template --output /caminho/novo/modelo.json
.venv/bin/audit3 --store /caminho/do/store review-completion ID --review /caminho/novo/modelo.json --output /caminho/novo/avaliacao-explicita.json
```

O código 0 de `--template` significa somente geração do rascunho. Esse comando
não aprova notas. O segundo comando sela o rascunho preenchido sem alterar o
contexto ao qual ele se refere e mantém pendências quando a revisão é insuficiente.

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
