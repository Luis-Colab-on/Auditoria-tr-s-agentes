> Documento histórico anterior à migração Codex Pro. Não execute comandos de API
> descritos aqui. Estado atual: [Codex Pro](codex-pro.md) e
> [validação atual](../validation/codex-migration.md). Reprovações históricas preservadas.

# Investigação da falha do teste de isolamento

**API desautorizada. Somente infraestrutura e fixtures sintéticas; FAEPA excluído.**

**Confirmação posterior:** o teste corrigido passou no Docker real do WSL na sessão
`20261110T181218Z-ebf02c03`, receipt `6555563b97dc2589808dfea4`, exit code 0, stderr
vazio e todos os probes registrados em stdout. [Evidência](../validation/20261110T181218Z-ebf02c03/evidence/isolation-receipt.json).
Os dois bloqueios novos pertencem ao Compose e são tratados na
[investigação seguinte](validacao-compose.md). O restante deste documento preserva
o diagnóstico e os resultados disponíveis antes dessa confirmação.

## Evidência recebida

A execução real do terminal WSL em `validation/20261110T175257Z-b27f80b7/`
teve **4 testes aprovados, 1 falho e 3 não executados**. Os quatro aprovados são
as fixtures `bug`, `clean`, `layered` e `rare`. As falhas esperadas de `bug` e `rare`
foram reproduzidas e seus testes de integração aprovaram; isso não equivale a quatro
auditorias por IA. No caso `bug`, 16 asserções continuam representando um mecanismo
conhecido, não 16 bugs.

Foram conferidos os checksums da sessão, os cinco receipts contra seus registros
autenticados, os manifests, scripts e hashes de stdout/stderr. A procedência está
registrada na [análise estruturada](../validation/isolation-fix-analysis.json).

Receipt de isolamento: `364cd6005111ff9aeb094e19`, run
`07b28a76c3cc877a1d0e1d63`. [Receipt, fonte e teste submetido](../validation/20261110T175257Z-b27f80b7/evidence/isolation-receipt.json).

| Campo | Observação |
|---|---|
| Execução | Docker real, versão 29.9.3 |
| Comando | `python -B /test/repro.py` |
| Imagem | `sha256:2199a62885a12290dc9c5be3ca0681d367576ab7bf037da120e564723292a2f0` |
| Exit code | 1 |
| Timeout | Não |
| stdout | Vazio, não truncado |
| stderr | `PermissionError: [Errno 13] Permission denied: '/root/.ssh'` |
| Ponto de interrupção | Linha 5 do script: `assert not Path('/root/.ssh').exists()` |

## Diagnóstico e alcance

A causa desta falha é **um erro no teste**. O código supunha que `Path.exists()`
sempre devolveria um booleano. Na execução registrada, a consulta ao caminho privado
lançou `PermissionError`, compatível com o usuário sem privilégios do container.
O teste encerrou por uma exceção que, nesse ponto, demonstra **acesso negado**.
Isso não determina se `/root/.ssh` existe, nem indica leitura de uma credencial.

O Docker iniciou o processo, portanto não se trata da ausência do daemon que havia
bloqueado as tentativas do sandbox. Essa falha também não demonstra escape de
isolamento. Não é uma conclusão baseada apenas em `status=failed`: o receipt,
traceback e script estabelecem o ponto de interrupção.

As asserções anteriores de variáveis de credencial e socket Docker não dispararam.
As tentativas posteriores de escrita na fonte e de conexão externa **não foram
alcançadas**. Elas continuam pendentes nessa execução; não se declara isolamento
integral aprovado com base nos quatro testes de fixtures ou no acesso SSH negado.

## Correção limitada ao teste

O helper [private_path_observation](../tests/probe_support.py) faz `stat()` explícito:

- `FileNotFoundError`: registra `absent`;
- `PermissionError`: registra `access_denied`, sem alegar ausência do caminho;
- consulta bem-sucedida: continua falhando com `credential directory visible`;
- qualquer outro erro: propaga e continua falhando.

A mesma função é copiada como código para a reprodução Docker. Os testes unitários
usam objetos controlados, sem consultar diretórios privados do host ou executar o
payload do container no controlador. [Regressões determinísticas](../tests/test_probe_support.py)
cobrem ausência, EACCES, EPERM, caminho visível, EIO, ELOOP e ENOTDIR.

O teste registra marcadores por verificação para permitir localizar uma futura
interrupção. Permanecem as verificações de credenciais, socket Docker, escrita negada
na fonte e conexões bloqueadas. Não se mudou o executor, imagem, usuário, mounts,
permissões, rede, capabilities, seccomp ou configuração Compose.

## Resultado após a correção

| Execução | Aprovados | Falhos | Não executados | Significado |
|---|---:|---:|---:|---|
| WSL original, antes da correção | 4 | 1 | 3 | Resultado histórico preservado |
| Regressões e unidade do executor | 21 | 0 | — | Infraestrutura; 1 teste Docker desmarcado pelo filtro |
| Nova tentativa no processo restrito | 0 | 0 | 8 | Sete sem acesso ao daemon; API desautorizada |
| Docker após correção no WSL normal | — | — | Pendente | Nenhum resultado novo recebido ainda |

[JUnit das 21 verificações](../validation/isolation-regression.xml) e
[relatório da tentativa restrita](../validation/20261110T180819Z-05b2a8de/report.md).
Não se promoveu o teste de isolamento a aprovado porque o código foi corrigido ou
porque os doubles passaram. O resultado Docker após a correção ainda precisa ser observado.

O usuário informou que construiu `audit3-browser:local` depois da execução original.
O motivo histórico de skip não deve ser apresentado como ausência atual da imagem.
Os dois casos Compose pendentes são **WordPress/PHP** e **Playwright/browser**;
ambos dependem da imagem do navegador no ambiente Compose atual. Só o segundo usa
Playwright. Suas execuções reais ainda precisam ser confirmadas.

## Reexecutar no terminal WSL

```bash
cd ~/projetos/auditoria-tres-agentes
.venv/bin/python scripts/validate_pending.py
```

O comando tenta os sete testes Docker, incluindo isolamento e os dois casos Compose.
Não precisa reconstruir imagens por esta correção, que altera apenas o teste montado
na execução. Não acrescente `--api`: o wrapper fixa `AUDIT3_LIVE_TEST=0` e remove a
chave da API do ambiente do subprocesso de testes, mesmo que o terminal a tenha.
O oitavo teste continuará não executado por falta de autorização nesta etapa.

Cada tentativa guarda novos receipts, stdout/stderr, hashes, JSON, Markdown e JUnit
em `validation/DATA-ID/`. Código de saída 2 pode significar apenas o teste de API
deliberadamente não executado; consulte os sete resultados Docker. Preserve a pasta
antiga para comparação. Uma falha nova deve ser investigada pelo receipt correspondente.
