# Segurança e fronteiras

O controlador autenticado não executa código do projeto, scripts enviados pelo modelo,
instalações do projeto ou comandos shell escolhidos pelo modelo. Apenas gerencia Git
com argumentos restritos e Docker/Compose. `prepare` nunca faz checkout e lê blobs
Git sem filtros; hooks, fsmonitor e configuração global são desativados. Não se reutilizam
tokens ChatGPT, credenciais GitHub, SSH agent ou configuração de produção.

Na aquisição local, somente o commit explícito é lido. Não se executa `git status`
na worktree recebida: esse comando pode acionar filtros `clean` da configuração
local, mesmo sem checkout. O manifesto registra
`tree_state=worktree_not_inspected_commit_only`; isso não afirma que a worktree
esteja limpa. Arquivos modificados e não rastreados permanecem intactos. Repositórios
bare registram `bare`, e ZIPs registram `no_git_history`. Quantidade, tamanho
individual e tamanho total são verificados antes de ler cada blob Git, inclusive
links excluídos; os links e submódulos nunca são seguidos ou executados.

`list_source`, `read_source`, `search_source`, `submit_test`, `read_evidence` são as únicas
ferramentas do runtime. Identidade, fase e run_id vivem em contexto/closures do controlador;
não são argumentos que o modelo pode trocar. Não há ferramenta para ler parecer privado,
editar receipt, executar eval/shell, publicar ou chamar outro agente. Falhas de ferramenta
são devolvidas sem caminhos locais privados, chaves ou stack traces.

O código e as narrativas são dados não confiáveis. Prompts instruem a ignorar comandos
embutidos; permissões não dependem dessa obediência. Uma injeção pode ainda prejudicar a
qualidade da análise, mas não deve ampliar capacidades. Testes offline provam barreiras
de ferramenta; resistência semântica de modelos reais à injeção ainda não foi medida.

ZIPs rejeitam traversal, caminhos absolutos/Windows/ADS, symlinks, arquivos especiais,
duplicação/case collision, expansão excessiva, arquivos criptografados e limites de volume.
Caminhos de leitura passam por normalização e verificação de symlinks. Fontes gravadas
recebem permissões somente leitura e hashes conferidos antes/depois de executar e em cada
leitura. Arquivos sensíveis/binaries/dependências/gerados são inventariados com razões,
sem seu conteúdo. Nomes sensíveis detectados também são substituídos por IDs opacos.

O scanner cobre padrões conhecidos de chaves/tokens, PEM, e-mails, CPF e atribuições
suspeitas. É **heurístico**, podendo omitir testes/configuração legítimos e deixar de
identificar PII, valores codificados ou formatos desconhecidos. O operador precisa
revisar a fonte e o inventário antes do envio. Dados sintéticos e requisitos previamente
sanitizados são a escolha recomendada. Não existe promessa de sanitização universal.

Registros JSON usam escrita atômica, fsync, hashes e HMAC com chave local privada. O
HMAC impede que o modelo, suas ferramentas ou um container fabriquem receipts; detecta
adulteração em disco sem conhecimento da chave. Não protege contra administrador/root
ou usuário local comprometido que pode ler a chave e alterar o programa. Não é uma
assinatura verificável por terceiros; checksums do ZIP detectam corrupção de transporte,
não estabelecem identidade criptográfica externa do executor.

Containers genéricos: network none, rootfs readonly, usuário sem privilégios, capacidades
removidas, no-new-privileges, PID/CPU/memória limitados, IPC privado, tmpfs e apenas fonte
e script montados readonly. Não montam socket Docker, HOME, SSH, token ou credencial real.
Inspeção após `create` verifica essas condições e bloqueia a execução se divergem. Os
processos Docker do controlador usam ambiente mínimo e nenhuma configuração remota do
Docker herdada. Imagens precisam ser confiáveis, adquiridas separadamente e fixadas em ID.

O helper de subprocessos do controlador cria uma sessão POSIX exclusiva. O timeout
cobre execução e drenagem dos pipes. Ao vencer ou receber cancelamento, o helper
encerra o grupo do subprocesso, incluindo filhos que herdaram stdout/stderr, e
permite até 0,25 segundo adicional para drenagem e coleta. A tolerância de limpeza
não amplia o tempo permitido de execução; agendamento do sistema impede prometer
retorno exato no milissegundo. Tempos observados de execução e encerramento são
informados nos receipts com timeout. Docker/Compose continuam responsáveis pela
remoção explícita dos containers: matar o cliente Docker não remove um container.

Os hashes de saída abrangem os bytes drenados antes da sanitização, inclusive os
que excedem o limite de retenção do texto. Se não houver EOF até o prazo de limpeza,
os pipes são fechados, as tarefas locais são canceladas e a saída é marcada como
incompleta e truncada. Nesse caso os hashes descrevem somente o prefixo observado,
com a insuficiência registrada no receipt. Essa contenção de processos confiáveis
do controlador não substitui o isolamento Docker do código auditado.

Compose usa apenas rede interna com gateway isolated, sem portas no host ou rede default.
Bloqueios HTTP do WordPress são defesa adicional: não substituem a rede, pois PHP, plugins,
navegador e comandos arbitrários podem usar sockets diretamente. MySQL e credenciais de
admin são sintéticos e descartáveis. Simuladores Asaas/Webmania/SMTP não reproduzem todos
os contratos comerciais, e retornam marcação explícita de simulação.

Docker não é isolamento completo contra vulnerabilidades de kernel/daemon. Use host/VM
dedicado, atualizado, sem dados de produção. O usuário controlador com acesso ao daemon
tem capacidade privilegiada no host. Em ambientes hostis, outra VM é recomendada; este
MVP não fornece hipervisor, gVisor ou garantia contra escapes. Testes reais de isolamento
e navegador ainda precisam ser executados onde Docker estiver disponível.

O runtime Codex não exporta traces de inferência. O leitor stdio descarta frames de
reasoning; registra apenas saída final observável, ferramentas, hashes e uso oficial.
O CLI pode manter sessões privadas em seu HOME específico; elas não entram no ZIP.
Não se promete retenção zero do serviço remoto. Consulte [Codex Pro](codex-pro.md)
para ambiente mínimo, catálogo com ferramentas locais removidas, perfis deny,
checagem de configuração efetiva, autenticação e bloqueio financeiro. Os controles
foram validados por parser/contrato e mocks; a integração com agentes reais continua
pendente. O runtime recusa configuração divergente e não habilita fallback.
