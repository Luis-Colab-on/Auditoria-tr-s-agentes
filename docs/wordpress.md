# WordPress, navegador e perfil FAEPA

**Referência atual:** o cenário sintético PHP/WordPress
`570af15e2192e19f73ddaff7` está encerrado, com 22 checagens aprovadas sob as extensões
autorizadas e a revisão local prevista. O [guia de uso](uso-versao-validada.md)
documenta comandos, parâmetros efetivos, evidências e limitações. A aprovação não
se estende a FAEPA ou outro projeto. Não repetir os testes encerrados por padrão.

O registro de infraestrutura de 10/11 descrito abaixo permanece como histórico
dos componentes existentes; naquele momento o smoke de agentes não havia ocorrido.

O perfil usa Compose com WordPress/PHP, MySQL, WP-CLI, simuladores/SMTP e Playwright.
A etapa de infraestrutura está **concluída**: na sessão WSL
`20261110T210248Z-0d1e3ccb`, o browser passou primeiro isoladamente e depois a suíte
terminou com **7 aprovados, zero falhas e 1 não executado**, o smoke dos agentes.
Os receipts, hashes, perfil seccomp efetivo e limpeza dos ambientes foram conferidos.
Veja [encerramento e próxima etapa](../validation/agents-readiness-20261110/report.md).
Não houve novas alterações nos componentes aprovados. O histórico de falhas permanece
nos relatórios [do browser](../validation/browser-chroot.md) e
[da rodada anterior](../validation/wsl-followup.md).
Tags de imagens são versões explícitas, não uma
alegação de serem as versões mais novas. Verifique disponibilidade e digests na fase
de aquisição; o runtime resolve e congela IDs locais antes de cada ambiente.

Nenhum wp-env existente foi encontrado neste projeto separado. Por isso há somente
um ambiente Compose, sem um segundo ambiente equivalente. Um wp-env de projeto
recebido é entrada não confiável: o MVP não o executa automaticamente. Uma integração
futura só deve reutilizá-lo após verificar todos os controles de rede/volumes/processos.

## Adquirir as imagens em ambiente habilitado

Esta seção é para instalação nova. Na correção atual, reutilize as imagens locais
já construídas; nenhum Dockerfile mudou.

Sem credencial da API no processo de build e sem source do plugin no contexto:

```bash
docker pull python:3.12.8-slim-bookworm
docker pull mysql:8.4.3
docker build -f src/audit3/assets/wordpress.Dockerfile \
  -t audit3-wordpress:local src/audit3/assets
docker build -f src/audit3/assets/browser.Dockerfile \
  -t audit3-browser:local src/audit3/assets
AUDIT3_WORDPRESS_TEST=1 pytest -q -m docker
```

O Dockerfile de WordPress usa estágios para copiar core e WP-CLI para uma imagem PHP
CLI sem volumes herdados. PHP, WordPress e WP-CLI são configuráveis pelos argumentos
de build/base e pelas imagens do perfil. Altere conscientemente o Dockerfile do operador
para extensões PHP adicionais; plugins dependentes de extensões ausentes ficam bloqueados.
O bootstrap copia core para tmpfs, instala site sintético, ativa o plugin e serve HTTP
interno em `wordpress:8080`. O core de teste não é ambiente de produção.

O banco é **MySQL 8.4**, sem substituição por SQLite. A configuração do perfil pode
selecionar outra imagem compatível, mas a compatibilidade precisa ser validada e registrada.
Não se declara compatibilidade com plugins comerciais ausentes. WooCommerce só é
ativado quando estiver na imagem; `woocommerce_required=true` bloqueia testes se estiver
ausente. Para incluí-lo, use imagem derivada com versão/checksum revisados copiados para
`/opt/audit3-plugins/woocommerce`; não baixe plugins durante os testes.

O perfil WordPress padrão define `db_memory_mb: 1024` para o MySQL, mantendo
`memory_mb: 512` nos demais serviços. O limite de swap é igual ao de memória;
nenhum serviço recebe memória ilimitada. Em perfil de operador, `db_memory_mb`
aceita de 128 a 4096 MiB. Quando ausente, herda `memory_mb`, preservando os perfis
congelados antigos. Alterações de recursos exigem nova preparação; `resume` não
troca os limites de uma execução existente. O template FAEPA permanece inalterado.

O perfil `faepa` é um **template de configuração**, não uma auditoria iniciada. Ajuste
slug, baseline, versões, extensões, WooCommerce e demais dependências em uma cópia
controlada do perfil. Nenhuma regra de negócio nem versão do FAEPA foi alterada e
seu código não foi acessado nesta tarefa. Só uma autorização futura deve iniciar
`prepare/run` para esse plugin.

## Testes e serviços internos

- `baseline`: argv do perfil, por padrão `php /source/tests/run.php`.
- `php`: reprodução em `/test/repro.php`, no WordPress sintético já inicializado.
- `wp-cli`: `wp --path=/work/wordpress eval-file /test/repro.php`.
- `browser`: Node/Playwright em container próprio, sem acesso à rede externa.

As chamadas HTTP/REST/AJAX devem ir a `http://wordpress:8080`. A fixture WordPress
contém REST público e AJAX protegido por nonce/capability. `examples/browser.cjs`
verifica REST, formulário de login administrativo sintético e rejeição de nonce AJAX.
Não conecta ao navegador pessoal do usuário. A versão do pacote Playwright acompanha
a versão da imagem; ela contém browsers, mas o pacote precisa ser instalado no build.
O exemplo mantém `chromiumSandbox: true`. Somente o runner browser recebe um perfil
seccomp com base Docker/Moby vendorizada e fixada por SHA-256, acrescida da regra de
`clone`, `setns` e `unshare` indicada pelo [Playwright](https://playwright.dev/docs/docker)
e da liberação de `chroot` exigida pelo sandbox de filesystem do Chromium.
A base condiciona `chroot` a `CAP_SYS_CHROOT` na configuração inicial do container;
como as capacidades externas são removidas, a syscall precisa de uma regra própria.
Isso não adiciona capacidade ao container. A autorização pelo kernel continua
necessária e o Chromium a obtém dentro de seu próprio user namespace. As demais
regras da base, inclusive
o retorno ENOSYS para `clone3` sem SYS_ADMIN, permanecem. A procedência está em
`src/audit3/assets/browser-seccomp-provenance.json`.

Compose carrega o JSON temporário; a inspeção exige seu conteúdo integral e recusa
perfil divergente ou `unconfined`. Mantém usuário não root, capacidades removidas,
`no-new-privileges`, rede internal+isolated, fonte readonly, IPC privado e limites.
Não altera AppArmor/sysctl do host. Se o host também impedir user namespaces, o
browser continuará falhando até haver evidência e suporte do ambiente; não há fallback
para Chromium sem sandbox. Os logs existentes não identificam qual política do host,
além da ausência do perfil necessário na configuração, está em efeito.

O SMTP local usa `wp_mail_from` para fixar `wordpress@audit3.example.invalid` antes
de WordPress chamar `PHPMailer::setFrom`. O hostname HTTP interno permanece
`wordpress`; não se altera DNS, validação de endereço nem a expectativa do teste.
O transporte continua restrito a `services:1025`, com captura local.

Esses assets são montados a cada execução e o perfil seccomp é consumido pelo
Compose no host controlador. **As correções não exigem rebuild de nenhuma imagem.**
Para revalidar no WSL normal com as imagens já existentes:

```bash
.venv/bin/python scripts/validate_pending.py --browser-first
```

`services:1025` captura SMTP em memória. `http://services:8080/mail` devolve mensagens
capturadas. `http://services:8080/asaas/...` e `/webmania/...` são simuladores genéricos
determinísticos, identificados por JSON e cabeçalho `X-Audit3-Simulator`. Adaptadores
do projeto precisam aceitar URLs locais configuráveis; domínios reais não são
redirecionados silenciosamente. Endpoints/erros específicos precisam de simuladores
mais fiéis antes de validar regras de integração. Nada envia e-mail, cobra ou acessa produção.

Todos os serviços comunicam-se apenas na rede internal+isolated. Não há portas publicadas,
socket do Docker nem volumes de produção. Fonte é readonly e banco/core/workdir são
descartados a cada reprodução. Os testes reais preparados verificam MySQL, captura de
e-mail, sockets para internet/metadata/host, credenciais, REST e navegador. Os payloads
Compose aprovaram PHP e browser na rodada WSL citada. A opção `--browser-first`
confirmou o cenário afetado antes da integração completa, com receipts/streams/JUnit
separados. O teste dos agentes e uma auditoria real continuam sendo etapas distintas;
a aprovação registrada não foi inferida de testes offline. A rede WordPress foi
verificada pelos seus próprios cenários, não inferida da aprovação do perfil genérico.
