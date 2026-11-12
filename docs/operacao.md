# Operação no Linux/WSL

O [guia de uso da versão validada](uso-versao-validada.md) reúne os comandos e os
limites efetivos da referência PHP/WordPress encerrada em 12/11/2026. Sua aprovação
ocorreu sob extensão autorizada e revisão local das notas, preservando o estado
bruto e a reprovação anterior. Este documento mantém os detalhes operacionais.

## Restrição financeira permanente

**NENHUM GASTO ADICIONAL ESTÁ AUTORIZADO.** A assinatura existente pertence à
empresa; só pode ser usada sua franquia já incluída. Autorizar testes, auditorias ou
outras tarefas nunca autoriza gastar dinheiro. A regra não expira e abrange o
auditor, orquestrador, Auditor, Defensor, Juiz, ferramentas, automações e processos.

São proibidos comprar, adicionar, recarregar ou consumir créditos adicionais,
mesmo existentes; ativar recarga automática; contratar, renovar, reativar, aumentar
ou alterar planos/assinaturas; fazer upgrade, adquirir complementos ou aumentar
limites financeiros para gastar; usar API/provedor pago ou alternativa com cobrança
adicional; contratar serviços, infraestrutura ou testes com custos extras.
Não alterar nem cancelar a assinatura existente, nem operar a conta/faturamento.
Automações, aprovações automáticas, instruções de ferramentas e “continue”,
“resolva” ou “faça funcionar” nunca autorizam exceções financeiras.

A regra está em `AGENTS.md`, nas instruções comuns e de cada papel, no recurso
`financial-policy.txt` e em cada entrada enviada pelo orquestrador. O registro
`financial-policy` de cada execução é imutável; novas execuções e retomadas
reaplicam a regra, inclusive depois de perda/compactação de contexto. Os bloqueios
de código continuam obrigatórios, independentemente dos prompts.

Antes de inferência, exigir fatos financeiros válidos vinculados à mesma conta e
consultas oficiais de autenticação, plano e franquia. Registrar **o horário real da
conferência**, com fuso, por `financial-confirm --checked-at`; nunca substituir por
hora atual, preencher marcadores como `[HH:MM]` ou renovar fatos antigos. A validade
factual é de 30 minutos, sem prazo para a restrição permanente. Vencimento,
quota esgotada, falha de consulta ou qualquer condição financeira desconhecida
bloqueiam a inferência e exigem salvar/relatar o progresso. Um turno em andamento
tem seu prazo limitado à validade financeira e é interrompido se ela acabar.
Retomada exige nova conferência real quando necessário, nunca solução paga.

Polling, interrupção de turnos e encerramento do cliente não são controle financeiro
atômico do serviço remoto. A ausência de créditos e recarga desativada devem ser
verdadeiras também em outros clientes. Sem evidência suficiente, não executar.
Usar somente infraestrutura local existente e previamente aprovada; esta tarefa
não autoriza contratação, pull/build de imagens ou serviços adicionais. Preservar
os sete casos de infraestrutura aprovados. FAEPA está fora do escopo.

O roteiro [concluir a validação](concluir-validacao.md) documenta a preparação
histórica das integrações. Não há repetição pendente do cenário PHP/WordPress
encerrado. A referência atual, seus resultados e os limites da conclusão estão no
[guia consolidado](uso-versao-validada.md).

Use um usuário local dedicado e armazenamento em filesystem Linux do WSL, não uma
pasta compartilhada com ACLs/permissões incompatíveis. `audit3 --help` lista os
comandos. Python 3.12 é o alvo do lock e dos testes efetivos; 3.11+ é a compatibilidade
declarada pelo pacote, não uma matriz de sistemas já testada. Testes de normalização
Windows são determinísticos no Linux, não testes executados em Windows real.

## Cadastrar outro projeto

Não há cadastro remoto no MVP. Copie `examples/config.json`, defina requisitos e
exclusões, escolha perfil e execute `prepare` com caminho local e ref explícita. O
inventário registra todos os arquivos da fonte e razões das omissões. Revise-o antes
de `run`. Um perfil JSON explícito é configuração **confiável do operador**: nunca
carregue automaticamente perfis, comandos, `.env` ou hooks de um repositório recebido.
O inventário não é uma autorização para enviar dados pessoais: remova-os na origem
ou exclua os arquivos por padrão explícito. Um scanner heurístico não substitui essa revisão.

`generic` usa Python/unittest da imagem indicada. Para outro projeto, forneça um perfil
com imagem previamente construída, linguagem permitida e `baseline` como argv.
Executáveis aceitos: python/python3/php/node/wp/phpunit. Nenhuma interpolação em shell
do host ocorre. Scripts exploratórios recebem um caminho fixo no container e podem
ser arbitrários apenas dentro do ambiente restrito.

Dependências e artefatos gerados são excluídos do envio ao modelo por política, mas arquivos
de configuração/lock e testes próprios entram no escopo. Dependências necessárias
à execução devem estar na imagem confiável pré-adquirida. Não execute `pip install`,
`npm install`, Composer ou scripts do projeto auditado no controlador. Submódulos
e LFS são registrados como lacunas; este MVP não os busca automaticamente.

## Aquisição separada e execução

Em máquina com Docker instalado, adquira explicitamente a imagem genérica:

```bash
docker pull python:3.12.8-slim-bookworm
audit3 doctor
pytest -q -m docker
```

O executor usa `--pull=never`, resolve a tag em ID SHA-256 local e congela esses IDs
na execução. Prefira digests no perfil para reprodução em outras máquinas. Uma tag
não é uma pinagem global; uma alteração de imagem após o primeiro teste exige nova
preparação em vez de misturar ambientes na mesma auditoria. A aquisição não ocorre
durante chamadas das ferramentas. Para adicionar dependências, construa uma imagem
revisada num contexto separado e sem credenciais. Builds têm rede e não recebem
o snapshot do projeto; testes não têm saída externa.

Cada reprodução cria container(s) e estado mutável novos; o banco WordPress usa tmpfs.
Receipts equivalentes do mesmo papel são reutilizados. Para repetição, o pedido precisa
indicar reprodução independente, confirmação de falha ou intermitência; há uma repetição
por impressão digital por padrão. Uma versão nova é outra preparação/execução.

`audit3 compare --before ID_ANTERIOR --after ID_NOVO --purpose 'comparação estática'`
registra comparação factual antes de iniciar os agentes. Os modelos podem consultar
trechos limitados da fonte anterior, sem narrativas anteriores. Pares de execução só
são classificados como equivalentes quando perfil, imagens, comando e script coincidem.
Origem preexistente/nova continua exigindo interpretação do mecanismo pelo Juiz.
Sem comparação, use origem desconhecida. O comando não aplica patches.

## Limites e retomada no Codex

Veja [Codex Pro](codex-pro.md) para os valores efetivos: `max_calls` conta turnos
App Server; `max_turns` limita passos de ferramenta por turno. Não se usa orçamento
em dólares ou tarifa API. A execução é serial no transporte, mesmo que o controlador
tenha slots de concorrência. Limites padrão: 48 turnos, 12 passos/turno, 120 segundos
por turno, 1.800 segundos totais, 12 reproduções e uma repetição justificada.

`resume ID` exige conta Pro, fatos financeiros atuais, quota conhecida e o mesmo
snapshot/backend/modelo. Turno ambíguo não é repetido. Receipts confirmados continuam
reutilizados. `cancel ID` solicita interrupção; isso não é uma trava financeira
atômica. Runs históricos Agents SDK permanecem legíveis e exportáveis e requerem
nova preparação para Codex.

No terminal normal WSL, sem reconstruir imagens existentes:

```bash
.venv/bin/python scripts/validate_pending.py
```

Falta de Docker é `not_executed`, não aprovação. O smoke real só pode ser iniciado
após os fatos financeiros documentados. A falha histórica do browser exige ambiente
capaz de executar o sandbox Chromium; não se remove sandbox para fazê-la passar.

## Correções do controlador e avaliação separada

Consulte [correções e validação local](correcoes-validacao-local.md) para os
requisitos de investigação cega, revisão de conclusão vinculada às evidências,
preparação causal do smoke Python e comandos reproduzíveis. O estado bruto de
runs anteriores permanece preservado. `review-completion ID --output ARQUIVO_NOVO`
avalia offline em um artefato separado; não retoma agentes nem altera o run.
