> Documento histórico anterior à migração Codex Pro. Não execute comandos de API
> descritos aqui. Estado atual: [Codex Pro](codex-pro.md) e
> [validação atual](../validation/codex-migration.md). Reprovações históricas preservadas.

# Bloqueio do Compose após confirmar o isolamento genérico

**API desautorizada. FAEPA fora do escopo.** Integração dos três agentes reais pendente.

**Confirmação posterior:** a sessão `20261110T184915Z-9e6b88f9` passou pela inspeção
dos quatro containers com mounts readonly e `Binds=null`, confirmando a correção
descrita abaixo. O novo bloqueio é na inicialização, tratado em
[validação do bootstrap](validacao-bootstrap.md). Os resultados anteriores permanecem preservados.

## O que foi executado no WSL

A sessão [20261110T181218Z-ebf02c03](../validation/20261110T181218Z-ebf02c03/report.md)
registrou **5 testes aprovados, 2 falhos e 1 não executado** no pytest.
Os checksums, receipts autenticados, manifests e hashes de stdout/stderr foram conferidos.
[Análise estruturada e IDs das imagens](../validation/compose-fix-analysis.json).

| Verificação | Resultado observado |
|---|---|
| Isolamento genérico | Aprovado em Docker, exit code 0, sem timeout, stderr vazio |
| Fixtures bug, clean, layered e rare | Quatro integrações aprovadas conforme suas expectativas |
| WordPress/PHP | Integração falhou porque o executor bloqueou o ambiente antes do teste |
| Playwright/browser | Integração falhou pelo mesmo grupo de verificações de segurança |
| Três agentes reais | Não executado: API desautorizada |

No [receipt de isolamento](../validation/20261110T181218Z-ebf02c03/evidence/isolation-receipt.json)
`6555563b97dc2589808dfea4`, stdout registra: credenciais de ambiente ausentes,
socket Docker ausente, acesso SSH negado, escrita na fonte negada e conexões aos três
endereços bloqueadas, seguido de `ISOLATION_PROBES_PASSED`. A imagem e fonte são as
mesmas da falha anterior de `Path.exists()`. Esta é a confirmação real da correção
daquele teste, limitada aos probes executados.

Os receipts [PHP](../validation/20261110T181218Z-ebf02c03/evidence/wordpress-php-receipt.json)
`46b340d6918cb7a40de113b7` e
[browser](../validation/20261110T181218Z-ebf02c03/evidence/wordpress-browser-receipt.json)
`86a0f342faf1c618d699cb72` registram ambos:

- `status=blocked`, `execution=not_executed`;
- exit code `null`, sem timeout;
- stdout/stderr vazios;
- motivo `Compose expõe host`.

São falhas dos critérios de integração, não falhas de asserções PHP/browser executadas.
As quatro imagens foram resolvidas em IDs locais antes do bloqueio, incluindo
`audit3-browser:local` (`sha256:f26e06b83e3af4b8cc04ff60dae4336365b934f092a8d295f2a2445239a1a057`).
Portanto, a falta da imagem já não explica esta rodada.

## Causa identificada no código e limite da evidência anterior

O aviso antigo reunia cinco condições: PID/IPC do host, dispositivos, portas publicadas
ou `HostConfig.Binds` não vazio. Ele era emitido durante a inspeção, **antes** de
iniciar os serviços. A inspeção detalhada não foi preservada nessa execução; não é
possível atribuir com certeza qual campo disparou apenas a partir desse receipt.
O aviso tampouco prova que uma credencial, porta ou filesystem do host tenha sido exposto.

Foi demonstrada uma incompatibilidade no gerador/validador: os mounts readonly
de fonte, teste e assets não especificavam `bind.create_host_path=false`. No código
oficial do Compose **5.7.0**, a geração pode usar a API antiga de `Binds` quando as
opções não exigem a Mount API; `create_host_path=false` exige a Mount API. O nosso
validador proíbe qualquer `Binds`, inclusive essa representação dos mounts previstos.
Fonte: [implementação oficial do Compose 5.7.0](https://github.com/docker/compose/blob/v5.7.0/pkg/compose/create.go#L1012-L1065),
[seleção da Mount API](https://github.com/docker/compose/blob/v5.7.0/pkg/compose/create.go#L1132-L1146),
blob `6787334f60a95a42ed8654cf7884579ff02bf1d9`.

Essa incompatibilidade está comprovada estaticamente e é consistente com o bloqueio
recebido. Sua eliminação precisa ser confirmada no WSL; não se assume que seja o único
obstáculo à inicialização ou ao navegador.

## Correção e garantias preservadas

Os mounts agora especificam `bind: {create_host_path: false}`. Os diretórios de origem
já são preparados pelo controlador, portanto não há necessidade de criação automática
pelo Docker. Fonte/testes/assets continuam readonly. O validador continua rejeitando
`HostConfig.Binds`, mounts inesperados/graváveis, socket Docker, PID/IPC host,
dispositivos, portas, rede extra, credenciais e privilégios indevidos.

O aviso agora identifica serviço e campo rejeitado. O controlador persiste um resumo
da inspeção e a etapa de preparação em `setup-diagnostics/ID`, com registro autenticado.
O resumo exclui valores de variáveis de ambiente. A validação exporta
`evidence/wordpress-php-setup.json` e `evidence/wordpress-browser-setup.json`, quando
a preparação chegar a essa etapa. Isso permite investigar novos bloqueios sem confundir
falha de montagem/inicialização com falha do script testado. A limpeza continua obrigatória.

## Testes da correção

**36 verificações de infraestrutura aprovadas**, 1 integração Docker desmarcada pelo
filtro, em [compose-regression.xml](../validation/compose-regression.xml).
Incluem configuração dos mounts, casos adversariais de segurança e um teste explicitamente
mockado que comprova recusa de `Binds`, ausência de início do payload, cleanup e persistência
do diagnóstico sem o canário de credencial. Mocks não validam Docker/Compose reais.

A [tentativa desta sessão](../validation/20261110T181849Z-531ab79f/report.md) após a correção
registrou 8 não executados: sete sem acesso ao daemon pelo sandbox e API desautorizada.
Ela não substitui nem invalida os cinco aprovados na execução WSL anterior. Os dois casos
Compose após a correção ainda aguardam execução no WSL normal.

```bash
cd ~/projetos/auditoria-tres-agentes
.venv/bin/python scripts/validate_pending.py
```

Não é necessário reconstruir imagens para esta mudança no controlador. Não use `--api`.
A nova sessão terá seu próprio relatório/receipts e preservará as execuções anteriores.
