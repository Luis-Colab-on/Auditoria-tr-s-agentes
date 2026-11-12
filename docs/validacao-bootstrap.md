> Documento histórico anterior à migração Codex Pro. Não execute comandos de API
> descritos aqui. Estado atual: [Codex Pro](codex-pro.md) e
> [validação atual](../validation/codex-migration.md). Reprovações históricas preservadas.

# Inicialização WordPress: coleta de evidências

**API desautorizada. Nenhum acesso ao FAEPA.** Os resultados de infraestrutura não
validam os três agentes reais, que continuam pendentes.

## Etapa efetivamente alcançada

**Última rodada: [20261110T190043Z-cc9824bc](../validation/20261110T190043Z-cc9824bc/report.md),
5 aprovados, 2 falhos e 1 não executado.** Agora há causa observada: nos dois
ambientes, o MySQL registrou `OOMKilled=true` com limite de 536.870.912 bytes
(512 MiB), e terminou com código 1. WordPress registrou conexões recusadas ao banco
e terminou com código 1, sem OOM. Os simuladores permaneceram ativos.

Os [logs/estados PHP](../validation/20261110T190043Z-cc9824bc/evidence/wordpress-php-setup.json)
e [browser](../validation/20261110T190043Z-cc9824bc/evidence/wordpress-browser-setup.json)
mostram `start_command.exit_code=0`, fase `wait_ready` e cleanup com código 0.
Os receipts continuam `blocked/not_executed`, sem código de saída de teste e sem
stdout/stderr do payload: **os dois testes pytest falharam porque seus ambientes
não ficaram prontos; as verificações PHP e navegador não chegaram a executar**.
Isso identifica um problema de recursos da infraestrutura, sem demonstrar falha
de isolamento ou defeito na fixture. Os 16 checksums exportados, os receipts e
diagnósticos autenticados e os hashes da fonte foram conferidos.

Foi adicionado `db_memory_mb=1024` ao perfil WordPress padrão. Somente o banco
passa a ter limite de 1 GiB; os outros serviços mantêm 512 MiB. Memória e swap
continuam limitados, com os valores efetivamente aplicados verificados antes do
start. Rede, mounts readonly, capabilities, usuário, processos, CPU e timeouts
permanecem iguais. O novo limite ainda precisa de confirmação em execução real;
os registros não medem pico de memória nem garantem que 1 GiB será suficiente.

Perfis já preparados conservam seus hashes e limites antigos: o campo opcional
ausente não é serializado. Essa compatibilidade foi verificada nos dois perfis
congelados desta rodada. O script de validação prepara novas execuções, que usam
o limite atualizado; não se modifica snapshot ou evidência histórica.

## Histórico da investigação

A sessão [20261110T184915Z-9e6b88f9](../validation/20261110T184915Z-9e6b88f9/report.md)
terminou com **5 aprovados, 2 falhos e 1 não executado**. O isolamento genérico e as
quatro fixtures passaram. Os dois payloads Compose não foram executados: seus receipts
têm `status=blocked`, `execution=not_executed`, exit code `null`, stdout/stderr vazios
e a limitação `WordPress não ficou pronto; bootstrap/compatibilidade pendentes`.

Os [diagnósticos PHP](../validation/20261110T184915Z-9e6b88f9/evidence/wordpress-php-setup.json)
e [browser](../validation/20261110T184915Z-9e6b88f9/evidence/wordpress-browser-setup.json)
confirmam que os quatro containers passaram pela inspeção, com `Binds=null`, mounts
readonly, rede interna, ausência de privilégios adicionais e limites configurados.
A fase atingida foi `wait_ready`; o cleanup terminou com código 0. Isso confirma a
correção anterior de declaração das montagens.

Esses dados não identificam por que WordPress/MySQL não ficaram prontos. Naquela
versão, `logging=none` descartava a saída dos serviços e seus estados finais não eram
coletados antes da remoção. Não é possível recuperar esses logs da evidência antiga.
Não se atribuiu a causa a memória, permissões, compatibilidade ou timeout sem dados.

## Coleta acrescentada

Os serviços `db`, `wordpress` e `services` usam logs **locais**, com `max-size=1m`,
`max-file=1` e `compress=false`. O runner mantém logging `none`. O controlador verifica
o driver e seus limites antes de iniciar os containers; não altera configuração do
daemon. A configuração segue o [driver local do Docker](https://docs.docker.com/engine/logging/drivers/local/).

Antes do cleanup, o controlador consulta somente os containers desta execução:

- estado do processo, código de saída, OOM, erro e timestamps;
- últimas 200 linhas de logs, com timeout de 10 segundos por consulta;
- até 16.000 bytes por stream, ou o limite configurado se menor;
- resultado do start e da última consulta de prontidão.

Os textos são sanitizados e não incluem dump de ambiente. Não há `--details` nem
streaming ilimitado. Hashes referem-se aos streams originais, portanto podem diferir
do texto sanitizado. Falhas de coleta ficam explícitas; não são resultados aprovados.
A remoção do ambiente permanece no `finally`, inclusive se a coleta falhar.

Os registros ficam nos arquivos `evidence/wordpress-php-setup.json` e
`evidence/wordpress-browser-setup.json`, também autenticados no store. A fonte,
read-only, rede, usuário, capabilities, memória, processos e espera de prontidão
permaneceram com os mesmos controles nessa etapa de instrumentação. A alteração
posterior de memória do banco é documentada acima. Não se elevou timeout para
ocultar o erro.

## Erro encontrado na própria coleta e corrigido

A primeira configuração de logs omitiu `compress=false`. O Docker habilita compressão
por padrão e recusou a combinação com `max-file=1`. A execução
[20261110T185832Z-fa1fe24f](../validation/20261110T185832Z-fa1fe24f/report.md) registrou
essa causa em `start_command.stderr`: `compression cannot be enabled when max file count is 1`.
Os serviços não chegaram a iniciar; esse foi **um erro introduzido na configuração
da coleta**, distinto do problema original em `wait_ready`.

A correção define `compress: "false"` e mantém um arquivo de 1 MB. A rodada
`20261110T190043Z-cc9824bc` confirmou que os serviços iniciaram e os logs foram
coletados. **47 verificações de infraestrutura passaram** após o ajuste de memória,
incluindo casos que recusam compressão incorreta e divergências de memória/swap.
[JUnit](../validation/startup-diagnostics-regression.xml).
Esses testes incluem doubles explicitamente identificados e não substituem Docker real.
A suíte offline completa também passou: **111 aprovados, zero falhas, 8 casos de
integração desmarcados**. [JUnit](../validation/offline-memory-fix-regression.xml).

A tentativa `20261110T185713Z-8e3d1302` foi interrompida (código 130), com um teste
concluído e sem chegar ao WordPress; não foi contada como validação do bootstrap.
A tentativa do sandbox `20261110T185625Z-ef6726a2` ficou sem acesso ao daemon.

[Análise estruturada, receipts e registros de procedência](../validation/startup-analysis.json).

## Próxima execução necessária

```bash
cd ~/projetos/auditoria-tres-agentes
.venv/bin/python scripts/validate_pending.py
```

Não acrescente `--api`; não é necessário reconstruir imagens. Aguarde o término,
que pode levar aproximadamente dois minutos sem nova saída no terminal. A próxima
rodada deve confirmar a inicialização do MySQL com 1 GiB e executar os payloads.
Não se declara WordPress, navegador ou três agentes operacionais enquanto isso não
for confirmado pelas evidências reais.
