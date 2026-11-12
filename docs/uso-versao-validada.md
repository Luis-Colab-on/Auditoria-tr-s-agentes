# Uso da versão validada do audit3

Referência atual encerrada em 12/11/2026: run **`e7a349ffa7b7bcdf47de1ab4`**, cenário
sintético pequeno PHP/WordPress. Esta página consolida a operação implementada e
o alcance demonstrado. Não inicia nem autoriza auditoria de outro projeto. FAEPA
permanece fora do escopo.

O pacote identifica-se como `audit3 0.2.0`; não foi criada uma nova tag de release.
O código utilizado está identificado pelos hashes e patches dos registros de
validação, não apenas pelo número do pacote.


**Publicação:** os artefatos operacionais indicados abaixo permanecem privados na
instalação local. O GitHub publica o [resumo revisado](../validation/public/README.md),
a fixture sintética e a configuração base, sem confirmações financeiras, identidade
de conta ou registros do cliente. Links para originais excluídos são referências
locais. Esta separação não altera os resultados nem os arquivos históricos.

## Resultado atual: execução real e reavaliação offline

Auditor, Defensor e Juiz participaram efetivamente com três chamadas concluídas
por papel, em sessões distintas: **nove chamadas e 894,828 segundos acumulados**.
Foram utilizados `gpt-6-astra`, esforço `max`, Standard (`default`) e o cliente
oficial isolado `0.167.0`. O controlador executado corresponde ao commit
`2fa7530183f11f074a68fa149f01cf9a1991447e`.

| Resultado | Estado preservado ou derivado |
|---|---|
| Execução real e julgamento | Nove fases concluídas; fonte e controles preservados |
| Estado operacional bruto | `partial`, `phase=done` |
| Aceitação histórica | **22/24**, preservada sem reescrever resultados |
| Reavaliação offline dos mesmos registros | **24/24**, conclusão revisada `completed` |
| Ressalvas narrativas examinadas | 72: 39 notas de escopo e 33 de procedimento; nenhuma bloqueante ou pendente para o objetivo |
| Avaliador da reavaliação | `scoped-assessment-5`, política `explicit-narrative-v1` |
| Suíte local final | **602 aprovados, zero falhas, oito integrações Docker/live não executadas na etapa offline** |

O baseline e as reproduções dos três papéis demonstram `(10, 3) → 13`, quando o
contrato exige `7`. As guardas de entradas inválidas e a autorização administrativa
foram preservadas. Os três IDs permanecem separados, com `root_cause_id=null`;
não são uma contagem de três defeitos independentes. A fixture mantém o defeito.

A política nova exige exame integral de cada mensagem e de suas afirmações,
requisitos originais, proveniência e predicados verificáveis sobre evidências
atuais. A interpretação semântica fica sob responsabilidade explícita do revisor;
um rótulo ou ponteiro não basta. Lacunas estruturais continuam bloqueantes.
Veja [revisão de conclusão](reprocessamento-local.md).

**A alteração mais recente do avaliador foi validada localmente, sem nova execução
real completa dos três agentes.** A aprovação 24/24 é uma derivação offline da
execução anterior, não uma execução da implementação modificada. O consumo agregado
de tokens e custo continua desconhecido; amostras oficiais não são somadas.

O [resumo público atual](../validation/public/integrated-20261112.json) não inclui
dados de conta ou sessões. Os originais ficam localmente em
`validation/integrated-20261112T183050Z-2fa7530/continuation-20261112T184227Z/`;
os resultados derivados ficam separados em
`validation/offline-review-e7a349f-20261112T195018Z/`. Esses diretórios privados
não acompanham o download do GitHub. A conferência de preservação verificou 200
arquivos históricos idênticos por hash.

O run atual autorizou até 1.500 segundos globais, 300 por turno e 16 chamadas,
somente com as tentativas previstas. Esses limites não se transferem para outro
run. A primeira suíte offline teve uma falha de ordem temporal no mock; o teste
isolado e a repetição integral passaram sem alterações. Os logs foram preservados
localmente. Não retomar nem repetir o run encerrado.

## Referência anterior e histórico preservado

O run anterior **`570af15e2192e19f73ddaff7`** e sua revisão anterior permanecem
preservados. Os números e links desta seção pertencem somente a essa referência,
sem substituir os resultados atuais acima.

Os três papéis leram o código e produziram reproduções reais em Compose. O Juiz
concluiu o julgamento: a reserva `(10, 3)` retorna `13`, contrariando o resultado
contratual `7`; as rejeições de entradas inválidas e a autorização administrativa
foram preservadas. A fixture continua com o defeito intencional.

- Configuração original do run: 16 chamadas, 120 segundos por turno e 900 segundos
  globais. O timeout inicial e seus dados de consumo desconhecido foram preservados.
- Ajuste autorizado: até 300 segundos por turno, sem aumentar chamadas ou slots.
- Sob o teto de 900 segundos, oito fases terminaram e o turno final foi interrompido.
  O registro encerrou em **900,040785 segundos e 10 chamadas**; essa reprovação
  histórica continua intacta.
- Extensão excepcional autorizada para **1.500 segundos acumulados**, restrita a
  `juiz/final`, no slot 1 que já existia. A continuação fez uma chamada nova do Juiz;
  nenhuma fase concluída foi repetida e nenhum contador foi zerado.
- Totais finais: **1.009,265799 segundos, 11/16 chamadas**, nove fases concluídas,
  nove chamadas concluídas e duas falhas históricas preservadas. As **22 checagens
  de aceitação passaram sob a extensão**, incluindo a revisão local prevista.

O estado bruto permanece `partial`, com `phase=done`: o runtime conservou mensagens
de limitação ainda não classificadas. Uma revisão local explícita das **66
mensagens**, com justificativas e referências às evidências, concluiu o escopo como
`completed`. Essa revisão não gerou inferência, não modificou os pareceres e não
converteu a reprovação histórica de 900 segundos em aprovação. `completed` significa
conclusão do escopo, não ausência de defeitos nem homologação de produção.

Os três IDs e vereditos foram preservados com `root_cause_id=null`. A aprovação não
dependeu de fusão causal PHP e não estabelece três defeitos independentes.

| Consulta da referência | Arquivo preservado |
|---|---|
| Resultado consolidado, totais e alcance | [result-summary.json](../validation/php-wordpress-final-extension-20261112/result-summary.json) |
| Resultado de cada uma das 22 checagens | [acceptance.json](../validation/php-wordpress-final-extension-20261112/acceptance.json) |
| Julgamento final original | [original-final-judgment.json](../validation/php-wordpress-final-extension-20261112/original-final-judgment.json) |
| Pareceres por papel/fase, fonte, cobertura e receipts | [real-report.json](../validation/php-wordpress-final-extension-20261112/real-report.json) |
| Exportação dos resultados originais e evidências publicadas | [three-agents.zip](../validation/php-wordpress-final-extension-20261112/three-agents.zip) |
| Estado bruto antes da revisão das notas | [unreviewed-raw-report.json](../validation/php-wordpress-final-extension-20261112/unreviewed-raw-report.json) |
| Revisão local, separada dos pareceres | [controller-review.json](../validation/php-wordpress-final-extension-20261112/controller-review.json) |
| Classificação de todas as mensagens, sem descarte automático | [limitation-classification-evidence.json](../validation/php-wordpress-final-extension-20261112/limitation-classification-evidence.json) |
| Conclusão revisada do escopo | [reviewed-completion.json](../validation/php-wordpress-final-extension-20261112/reviewed-completion.json) |
| Autorização da extensão global | [global-extension-authorization.json](../validation/php-wordpress-final-extension-20261112/global-extension-authorization.json) |
| Reprovação original sob 900 segundos | [historical-900-acceptance.json](../validation/php-wordpress-final-extension-20261112/historical-900-acceptance.json) |
| Preservação e hashes das evidências | [preservation.json](../validation/php-wordpress-final-extension-20261112/preservation.json), [artifact-sha256.json](../validation/php-wordpress-final-extension-20261112/artifact-sha256.json) |

Os registros anteriores continuam em `validation/php-wordpress-smoke-20261111/` e
`validation/php-wordpress-timeout-20261112/`. O histórico Python encerrado também foi
preservado. Os hashes documentam o código de cada etapa e não são atualizados
retroativamente.

**Não retomar nem repetir o run de referência.** Ele está encerrado. Os roteiros
em `validation/` são vinculados aos respectivos IDs, autorizações e tentativas;
não são inicializadores genéricos para outros projetos.

## Restrição financeira e ambiente

A [restrição financeira permanente](../AGENTS.md) continua integralmente vigente:
somente a franquia já incluída na assinatura existente. Não comprar, recarregar ou
consumir créditos adicionais, ativar recarga, alterar/contratar/cancelar assinatura,
usar API ou fallback pago, nem contratar serviços com custos extras. Autorizações
de trabalho ou de tempo operacional nunca autorizam gastos.

Antes de cada inferência, o controlador exige conta/plano e franquia oficialmente
confirmados e fatos do operador, vinculados à mesma conta, de **créditos adicionais
zero e recarga automática desativada**. A conferência vale 30 minutos a partir do
horário real informado; nunca use a hora atual para renovar um fato antigo. Fatos
vencidos, quota bloqueada ou condição desconhecida interrompem a inferência.

O protocolo não expõe o estado da recarga automática; essa informação depende do
painel conferido pelo operador. Consultas de quota e cancelamento não são uma trava
financeira atômica. Não há garantia técnica de cobrança zero que substitua esses
fatos; valores desconhecidos não são tratados como zero. O uso da franquia já foi
autorizado, sem autorização para operações no faturamento.

Use a instalação Linux/WSL existente: Python 3.12, `.venv`, Codex CLI **0.167.0**,
Docker Engine 28+ e Compose. Reutilize as imagens locais aprovadas
`audit3-wordpress:local`, `mysql:8.4.3`, `audit3-browser:local` e
`python:3.12.8-slim-bookworm`. O executor congela seus IDs e usa `--pull=never`.
Ausência ou incompatibilidade bloqueia a execução; este guia não manda instalar,
adquirir, reconstruir ou atualizar imagens. A inicialização sintética do WordPress
e do banco ocorre dentro dos containers descartáveis.

Mantenha o mesmo Store absoluto, com seu HOME privado e login oficial. Não copie
`auth.json`, tokens ou `.integrity-key` para relatórios, outro projeto ou outro Store.
Uma instalação/login novo tem procedimento próprio em [Codex Pro](codex-pro.md).

## Cliente oficial isolado 0.167.0

O auditor resolve `codex` pelo PATH e executa o binário nativo oficial. Na
instalação WSL x86_64 usada na validação, selecione o cliente separado assim:

```bash
cd "$HOME/projetos/auditoria-tres-agentes"
AUDIT3_RAIZ="$PWD"
AUDIT3_STORE="$AUDIT3_RAIZ/.audit3"
AUDIT3_CLIENTE="$HOME/.local/share/audit3/clients/codex-0.167.0"
AUDIT3_CODEX_BIN="$AUDIT3_CLIENTE/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin"

audit3_python() {
  PATH="$AUDIT3_CODEX_BIN:$PATH" "$AUDIT3_RAIZ/.venv/bin/python" "$@"
}

test -x "$AUDIT3_CODEX_BIN/codex"
"$AUDIT3_CODEX_BIN/codex" --version
audit3_python -c 'from audit3.codex_policy import executable; print(executable())'
```

O resultado de versão deve ser **`codex-cli 0.167.0`** e o caminho resolvido deve
estar nessa instalação isolada. O diretório vem da distribuição oficial
`@openai/codex@0.167.0`; não contém o código do projeto nem o HOME de autenticação
do auditor. Se não existir, obtenha a versão exata pela distribuição oficial em
diretório separado antes de continuar. Não substitua silenciosamente por outra
versão nem altere o verificador. Em outra arquitetura, use o binário oficial
correspondente, sem reutilizar o caminho x86_64.

A função só define PATH no processo chamado. Não execute `export PATH`, não edite
arquivos de inicialização do shell e não substitua o cliente global `0.167.2`.
Repita a definição da função em outro terminal quando precisar dela. As sessões e
configurações dos demais projetos permanecem separadas do HOME privado do auditor.

Antes de uma futura auditoria autorizada, verifique o contrato local:

```bash
audit3_python "$AUDIT3_RAIZ/scripts/verify_codex_contract.py"
audit3_python -m audit3.cli --store "$AUDIT3_STORE" doctor
```

O verificador testa configuração, protocolo e ferramentas com sessões temporárias
sem `turn/start`, sem login e sem inferência. O contrato deve retornar `passed` e
`client_version: 0.167.0`. Isso não confirma a conta nem a franquia.

Reutilize o login privado existente. Somente para um Store sem preparação/login:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" codex-setup
```

Execute no terminal o comando de login oficial que ele mostrar. Não copie
credenciais pessoais. Depois siga a preparação, a conferência factual e o
preflight das próximas seções; somente então use `run --prepared`.

## Preparar uma cópia local e delimitar o escopo

Os blocos seguintes documentam **uma futura auditoria local expressamente
autorizada**, não uma execução nesta etapa. Substitua os caminhos e marcadores
antes de usá-los. Não aponte para FAEPA nem para o run encerrado de referência.

Selecione primeiro o [cliente isolado](#cliente-oficial-isolado-01670).
Os comandos deste guia usam `audit3_python`, definido nessa etapa, para manter o
PATH específico somente nos processos do auditor.

Na raiz da instalação existente:

```bash
cd "$HOME/projetos/auditoria-tres-agentes"
umask 077
AUDIT3_RAIZ="$PWD"
AUDIT3_STORE="$AUDIT3_RAIZ/.audit3"
AUDIT3_ORIGEM='/caminho/local/do-projeto-autorizado'
AUDIT3_TRABALHO='/caminho/local/da-operacao-autorizada'
AUDIT3_COMMIT='SUBSTITUA_PELO_SHA_COMPLETO_REVISADO'
mkdir -p -- "$AUDIT3_TRABALHO"

git -c core.hooksPath=/dev/null clone --local --bare --no-hardlinks \
  "$AUDIT3_ORIGEM" "$AUDIT3_TRABALHO/fonte.git"

cp -- validation/php-wordpress-smoke-20261111/config.json \
  "$AUDIT3_TRABALHO/config.json"
```

Essa cópia Git é local, privada e sem checkout: não executa o projeto. `prepare`
lerá os objetos do commit explícito e criará o snapshot readonly em
`STORE/RUN/source/`. Alterações não commitadas do diretório original não entram.
O histórico da cópia Git não é integralmente enviado ao modelo; somente os arquivos
inventariados do commit selecionado entram no snapshot.

A configuração copiada é a **base de 16 chamadas / 120 segundos / 900 segundos**.
Ela não herda as exceções de 300/1.500 segundos do run encerrado. Também não garante
tempo suficiente para outro projeto. Revise o escopo e os limites autorizados antes
de preparar; não importe assinaturas ou autorizações operacionais de outro run.

Prepare `"$AUDIT3_TRABALHO/requisitos.txt"` com o contrato funcional, a raiz do plugin,
entradas e invariantes relevantes, testes próprios e exclusões explícitas. Registre
o que pode e o que não pode ser concluído. Não predetermine achados ou vereditos.
Para PHP, peça IDs separados e `root_cause_id` nulo ou exclusivo quando não houver
prova suportada de equivalência. Não imponha uma contagem de defeitos por ID.

Remova dados reais, dumps, uploads, segredos e dependências desnecessárias de uma
cópia de escopo autorizada. `exclude` e `prior_reports` são listas do config do
operador. Dependências/artefatos/segredos identificados ficam registrados como
omissões; omissões podem bloquear conclusão. Não use exclusões para declarar
cobertura completa de código que não foi analisado. Relatórios anteriores ficam
em quarentena até a barreira; o modelo não deve recebê-los como autoridade inicial.

Se o escopo sanitizado não corresponde a um commit, use um ZIP local revisado em
vez de fingir que alterações locais pertencem ao SHA. O ZIP deve conter os arquivos
na raiz correta do plugin, sem um diretório externo adicional. Não inclui histórico
Git nem recebe `--ref`. Não execute Composer, npm, scripts ou hooks do projeto no
host para prepará-lo. Submódulos e LFS não são materializados automaticamente.

O perfil `wordpress` aprovado exige um plugin compatível com o bootstrap e o
baseline **`php /source/tests/run.php`**. Seu slug é `synthetic-plugin`. Para um
plugin com outra estrutura, confira slug, baseline e dependências antes do preparo;
se necessário use uma cópia explícita e confiável de
`src/audit3/profiles/wordpress.json`. Alterar o perfil exige nova preparação e não
transfere a validação da fixture para dependências ou projetos ainda não testados.
Não carregue perfis ou comandos automaticamente da fonte recebida.

Preparação Git com o perfil existente:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" prepare \
  --repo "$AUDIT3_TRABALHO/fonte.git" --ref "$AUDIT3_COMMIT" \
  --profile wordpress --config "$AUDIT3_TRABALHO/config.json" \
  --requirements "$AUDIT3_TRABALHO/requisitos.txt"
```

Alternativa ZIP, **em lugar** da preparação Git:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" prepare \
  --repo "$AUDIT3_TRABALHO/fonte.zip" \
  --profile wordpress --config "$AUDIT3_TRABALHO/config.json" \
  --requirements "$AUDIT3_TRABALHO/requisitos.txt"
```

`prepare` não inicia modelos. Copie o ID retornado e revise o inventário antes de
`run`. Cada `prepare` cria outro run; não use o comando como retry de uma falha.

```bash
AUDIT3_RUN='SUBSTITUA_PELO_ID_RETORNADO'
audit3_python - "$AUDIT3_STORE" "$AUDIT3_RUN" <<'PY'
import json, sys
from pathlib import Path
from audit3.evidence import Store
m = Store(Path(sys.argv[1])).get(sys.argv[2], 'manifest')
print(json.dumps({k: m[k] for k in
    ('run_id', 'source_id', 'requirements', 'files', 'limitations')},
    ensure_ascii=False, indent=2))
PY
```

## Conferência financeira e preflight sem inferência

Consulte a mesma conta autenticada pelo mecanismo oficial:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" doctor --probe-codex \
  > "$AUDIT3_TRABALHO/doctor.json"
```

Esse comando consulta conta/modelo/quota sem criar turnos. Preserve o `plan`
recebido e consulte esse metadado somente no ambiente local. Não publique o JSON de
conta. Copie `official_metadata.account_fingerprint`
do JSON local. Ele é um hash de vinculação, não um token. O sucesso de `doctor`
sozinho não substitui a conferência factual nem o preflight financeiro completo.

Confira no painel da mesma conta os dois fatos. Só depois registre o horário real
com data e fuso, sem aproveitar uma confirmação vencida:

```bash
AUDIT3_FINGERPRINT='SUBSTITUA_PELO_HASH_OFICIAL_DO_DOCTOR'
AUDIT3_CHECKED_AT='SUBSTITUA_PELO_HORARIO_REAL_ISO8601_COM_FUSO'
audit3_python -m audit3.cli --store "$AUDIT3_STORE" financial-confirm "$AUDIT3_RUN" \
  --account-fingerprint "$AUDIT3_FINGERPRINT" \
  --auto-recharge disabled --extra-credits none --checked-at "$AUDIT3_CHECKED_AT"
```

Não há subcomando CLI `preflight`. A chamada existente abaixo faz o preflight
completo separadamente, sem inferência e sem tocar em slots ou iniciar Docker:

```bash
audit3_python - "$AUDIT3_STORE" "$AUDIT3_RUN" <<'PY'
import asyncio, json, sys
from pathlib import Path
from audit3.evidence import Store
from audit3.workflow import Workflow
from audit3.codex_runtime import CodexRuntime
from audit3.snapshot import verify_source

async def check():
    store = Store(Path(sys.argv[1]))
    workflow = Workflow(store, sys.argv[2])
    verify_source(store, workflow.manifest)
    runtime = CodexRuntime(store, sys.argv[2], workflow.config)
    try:
        result = await runtime.preflight()
        print(json.dumps({k: result[k] for k in
            ('authentication', 'plan', 'financial')}, ensure_ascii=False, indent=2))
    finally:
        await runtime.close()

asyncio.run(check())
PY
```

Falha ou estado financeiro desconhecido bloqueia o próximo passo. O runtime repete
as verificações antes da inferência; um preflight anterior não libera fatos vencidos.
Não há API paga, compra de créditos ou fallback como alternativa ao bloqueio.

## Iniciar, acompanhar, interromper e retomar

Com escopo revisto, fatos válidos e preflight aprovado, o comando de inferência é:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" run --prepared "$AUDIT3_RUN"
```

O Workflow usa o baseline congelado ou o executa em Docker/Compose antes dos
agentes. Modelos recebem trechos remotamente pela OpenAI; testes da fonte rodam
somente no executor local descartável. Falha de instalação/execução não comprova
defeito. Um exit code diferente de zero exige leitura do receipt e interpretação
das expectativas do teste.

Em outro terminal, na mesma raiz e com as mesmas variáveis/Store, acompanhe:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" status "$AUDIT3_RUN"
```

`status` lê estado e ledger. As fases podem ser `initial-0000`, `blind`, `contest`,
`reply`, `review`, `final` e `done`. Fases extras só aparecem pelo protocolo de nova
evidência material. `elapsed_seconds` é consolidado ao sair da execução ativa; não
o interprete como contador em tempo real durante um turno.

Para solicitar interrupção de uma execução ativa:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" cancel "$AUDIT3_RUN"
```

Após diagnosticar a interrupção, confirmar que há fase e tentativa disponíveis e
renovar **somente por nova conferência real** os fatos que tenham vencido, execute
o preflight acima e então:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" resume "$AUDIT3_RUN"
```

`resume` usa o mesmo ID, snapshot, backend, modelo, conta, Store e sessões dos
papéis; reaproveita fases validadas e receipts equivalentes conforme o fluxo.
Mantém chamadas, tentativas e tempo acumulados. Não use `prepare` para contornar
uma fase bloqueada nem coloque `resume` em loop automático.

Timeout/perda de transporte pode deixar checkpoint `ambiguous`. `resume` não o
repete automaticamente: exige consulta oficial do turno e revisão explícita da
interrupção, vinculada ao checkpoint e a um slot já existente. A CLI não tem uma
flag genérica para resolver ambiguidade, abrir slots ou conceder extensões. Não
edite JSON autenticado, marcadores ou timestamps manualmente. Roteiros históricos
de recuperação não devem ser aplicados a outro run.

Se `phase=done`, `resume` retorna o estado salvo sem nova inferência. Não transforma
um estado bruto `partial` em aprovação revisada. A CLI usa código de saída 2 para
resultados diferentes de `completed`; leia o relatório para distinguir limite,
bloqueio, conclusão de fases e revisão das notas.

## Pareceres, evidências e resultado

Para um futuro run em andamento ou encerrado, os comandos existentes são:

```bash
audit3_python -m audit3.cli --store "$AUDIT3_STORE" report "$AUDIT3_RUN"
audit3_python -m audit3.cli --store "$AUDIT3_STORE" export "$AUDIT3_RUN" \
  --output "$AUDIT3_TRABALHO/resultado.zip"
```

Eles geram relatórios/exportações locais, sem modelos. `report` atualiza arquivos
derivados do Store; `export` usa leitura e cria um destino novo. Para runs
encerrados, leia os artefatos preservados. Para revisar a conclusão separadamente,
use `review-completion`, conforme o [procedimento offline](reprocessamento-local.md).

| Informação | Store ou relatório |
|---|---|
| Fonte/inventário, hashes e escopo | `manifest`, `source/`; campo `manifest` no relatório |
| Parecer por papel e fase | `roles/<papel>/phases/<fase>`; campo `opinions` |
| Pareceres cegos congelados | `roles/<papel>/initial` e `barrier` |
| Julgamento final | `judgment`; campos `judgment`, `findings`, `verdicts` |
| Scripts e execuções | `tests/<ID>`, `receipts/<ID>`, `setup-diagnostics/<ID>` |
| Eventos e chamadas | `events/`, `ledger`, `codex-turns/`; campo `usage` |
| Estado operacional | `state`; campos `state`, `coverage`, `completion_assessment` |
| Contexto efetivo e extensões específicas | `runtime`, `runtime-binding`, `operational/` |

Os JSON internos do Store são envelopes autenticados; use `Store.get` para leitura
verificada. Não os trate como arquivos de configuração editáveis. Antes da barreira,
evidências dos outros papéis não são publicadas. A observação intermediária do
controlador distingue `executed_hidden_by_barrier` de `not_executed` e de tentativa
sem receipt, cujo resultado é desconhecido. Isso não libera acesso cruzado.

O ZIP padrão inclui resultados e evidências publicadas selecionadas, não todo o
Store nem toda revisão externa. Na referência, mantenha também `controller-review`,
aceitação, autorizações, hashes e histórico listados acima. Não compartilhe a raiz
privada do Store como se fosse um relatório.

## Modelo, esforço e limites efetivos

Nos três papéis foram confirmados `gpt-6-astra`, esforço **`max`**, Standard
(`serviceTier=default`). A autenticação exigida é `chatgpt`; os metadados da conta
e o valor do plano consultado permanecem locais. O código só
seleciona `xhigh` quando `max` não está no catálogo oficial; esse fallback não foi
o esforço usado neste run. Não há troca automática para outro provedor pago.

| Parâmetro | Base pública / run anterior | Autorizado no run atual | Defaults sem config / `examples/config.json` |
|---|---:|---:|---:|
| Chamadas App Server (`max_calls`) | 16 | 16 | 48 |
| Tempo por turno (`call_timeout`) | 120 s | até 300 s, autorizado | 120 s |
| Tempo global acumulado | 900 s | 1.500 s desde a preparação | 1.800 s |
| Passos de ferramenta por turno (`max_turns`) | 12 | 12 | 12 |
| Tempo do processo de teste (`test_timeout`) | 60 s | 60 s | 60 s |
| Novas reproduções (`max_reproductions`) | 12 | 12 | 12 |
| Repetições justificadas por fingerprint (`max_repeats`) | 1 | 1 | 1 |
| Correção de saída inválida | no máximo 1 | slots existentes, sem reposição | no máximo 1 |
| Retry transitório do controlador | 0 | 0 | 0 |
| Concorrência de invocações | 1 | 1 | 1 |
| Entrada/saída máxima | 250.000 / 64.000 bytes | iguais | iguais |
| Lote/leitura de fonte | 600 / 160 linhas | iguais | iguais |

O prazo efetivo é sempre limitado também pela validade financeira e pelo tempo
global restante. Extensão operacional não é autorização financeira e não é
herdada por outro run. Não alterar o config congelado para modificar limites.

`max_calls` conta turnos do App Server, não cada request/retry interno do cliente.
O timeout do processo de teste não representa sozinho todo o tempo de bootstrap
e limpeza do Compose. Campos legados como `budget_usd`, `call_reserve_usd` e
`max_output_tokens` não limitam cobrança nem a geração Codex nesta implementação.
Não converter a franquia em dólares nem somar amostras cumulativas de threads como
se fossem consumo por turno. O total agregado de tokens/custo do run é desconhecido.

## Limitações da conclusão e da versão

- A validação cobre este cenário pequeno, os fluxos e controles exercitados; não
  comprova qualidade geral de auditorias arbitrárias ou de todo plugin WordPress.
- Foi comprovado retorno aritmético errado; não foram demonstrados estoque persistido
  incorreto, exposição da reserva pelo GET ou ocorrência em produção.
- Autorização foi exercitada por despacho REST interno e `wp_set_current_user`,
  sem autenticação HTTP externa nem configurações personalizadas de capacidades.
- Inteiros máximos, coerções fora do domínio documentado e cobertura exaustiva de
  execução não foram testados. Leitura completa e cobertura dinâmica são medidas
  diferentes. Ausência de comparação assinada mantém a origem temporal desconhecida.
- Defeitos PHP individuais admitem reprodução real com receipt ou demonstração
  estática referenciada. O verificador causal disponível é limitado a Python e não
  prova equivalência PHP. Manter IDs separados permite julgar cada alegação; não
  transforma duplicatas possíveis em defeitos independentes comprovados.
- Dependências, extensões, plugins e imagens ausentes bloqueiam reprodução; não há
  instalação ou alternativa paga automática. Compatibilidade adicional exige
  autorização, evidências e validação próprias.
- O contrato Codex fixado em 0.167.0 usa recursos experimentais/beta. Mudança do
  cliente não equivale à versão validada; não atualizar silenciosamente.
- Revisão de conclusão não é automática: mensagens desconhecidas ou não esclarecidas,
  lacunas relevantes, fases pendentes e achados sem contraditório continuam bloqueantes.
  A revisão externa precisa vincular objetivo, contexto, texto preservado e evidências.
  Ela não substitui parecer, julgamento ausente ou nova execução real.

Detalhes dos registros de revisão estão em [reprocessamento local](reprocessamento-local.md).
As regras de isolamento e execução permanecem em [operação](operacao.md),
[Codex Pro](codex-pro.md) e [WordPress](wordpress.md). Nenhuma extensão deste histórico
autoriza nova auditoria ou qualquer gasto adicional.
