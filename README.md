# audit3

**Restrição financeira permanente:** [nenhum gasto adicional está autorizado](AGENTS.md).
Somente a franquia da assinatura existente da empresa; créditos adicionais, recarga,
mudanças de assinatura e alternativas pagas são proibidos. A regra não expira.
Fatos financeiros vencidos ou desconhecidos bloqueiam inferência.

Auditor, Defensor e Juiz em três sessões distintas do **Codex oficial**, controlados
por Python. Modelo solicitado nos três papéis: `gpt-6-astra`, Max (`max`), Standard
(`default`). Extra High (`xhigh`) só é selecionado se Max não constar do catálogo.
Não há gerente modelo, subdelegação, Fast, Ultrafast ou fallback pago.

**Execução real dos três agentes concluída na fixture sintética PHP/WordPress.**
O run `e7a349ffa7b7bcdf47de1ab4`, executado com o controlador `2fa7530`, terminou
com nove chamadas concluídas e 894,828 segundos acumulados. A aceitação histórica
permanece em **22/24**, com estado bruto `partial` e fases concluídas.

A reavaliação **offline** dos mesmos registros aprovou **24/24** após revisar as
72 ressalvas narrativas: 39 notas de escopo e 33 de procedimento. A política
`explicit-narrative-v1` vincula cada decisão ao objetivo, texto integral, origens,
revisor e evidências atuais, preservando os bloqueios estruturais e os originais.
A suíte local final teve **602 testes aprovados, zero falhas e oito integrações
Docker/live não executadas nessa etapa offline**.

**A última alteração do avaliador não passou por uma nova execução real completa.**
A aprovação derivada refere-se à execução anterior; não demonstra auditorias de
projetos arbitrários nem homologação de produção. FAEPA permanece fora do escopo.

Consulte o **[guia de uso da versão validada](docs/uso-versao-validada.md)** para
preparação local, delimitação de escopo, comandos exatos, conferência financeira,
início, acompanhamento, retomada, limites, resultados e limitações. Os
[resultados públicos consolidados](validation/public/integrated-20261112.json)
distinguem o resultado histórico da reavaliação. Os registros completos permanecem
privados na instalação local; não repetir seus roteiros de execução.

A infraestrutura WSL aprovada em `20261110T210248Z-0d1e3ccb` e o histórico Python
encerrado foram preservados. O [texto anterior de status](docs/historico-status-readme-20261112.md)
foi arquivado com suas referências, sem apagar falhas ou evidências anteriores.

## Instalação

Python 3.12 é o alvo testado (pacote admite 3.11+). Use o **Codex CLI 0.167.0**
oficial em instalação isolada. O contrato experimental é fixado nessa versão. O projeto
não instala SDK de inferência, Agents SDK ou segunda linguagem.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q -m 'not docker and not live'
```

O [procedimento do cliente isolado](docs/uso-versao-validada.md#cliente-oficial-isolado-01670)
seleciona o executável pelo PATH somente dos processos do auditor, preservando o
cliente global `0.167.2` e as configurações de outros projetos. Inclui a verificação
local `scripts/verify_codex_contract.py`, `doctor` e `codex-setup`.
Se precisar de um login novo, execute o comando mostrado por `codex-setup`: ele usa
`codex login --device-auth` no HOME privado do auditor. Nunca forneça senha, token,
cookie ou cartão ao audit3. O Codex pessoal e suas variáveis globais não são alterados.
`audit3 doctor --probe-codex` consulta metadados oficiais sem iniciar turnos.

## Preparar e executar

Siga o [guia consolidado](docs/uso-versao-validada.md), incluindo revisão do
inventário, fatos financeiros válidos e preflight antes de `run` ou `resume`.
`prepare` cria um snapshot e outro ID; não serve como retry. As extensões da
referência são específicas daquele run, não defaults para novas auditorias.

As ferramentas do controlador liberam trechos para processamento remoto pela
OpenAI. A fonte sob teste executa somente em Docker/Compose descartável, sem HOME
pessoal, credenciais Codex, socket Docker ou produção. Não há correção automática,
push ou publicação do código auditado. Condição financeira desconhecida bloqueia
inferência, sem fallback pago.

## Verificação e documentação

A referência aprovada já está encerrada. Não é necessário repetir testes para
consultá-la ou usar este guia. Se uma revalidação for explicitamente solicitada
no futuro, o comando existente de infraestrutura é:

```bash
.venv/bin/python scripts/validate_pending.py
```

Esse comando executa as sete verificações Docker e deixa o smoke Codex sem execução.
O smoke, a confirmação financeira, retomada e limitações estão em
[Codex Pro](docs/codex-pro.md). Não execute antigos comandos `--api` ou
`doctor --probe-api`: eles falham com explicação antes de acessar a API.

- [Uso da versão validada](docs/uso-versao-validada.md)
- [Arquitetura e barreira](docs/arquitetura.md)
- [Segurança](docs/seguranca.md)
- [Operação](docs/operacao.md)
- [WordPress e browser](docs/wordpress.md)
- [Resultado atual e limites da validação PHP/WordPress](validation/public/integrated-20261112.json)
- [Preparação histórica dos agentes em 10/11](validation/agents-readiness-20261110/report.md)

Resultados anteriores em `validation/` e documentação histórica identificada como
anterior à migração mantêm suas versões e reprovações. Runs Agents SDK podem ser
lidos/exportados; não podem ser retomados como se fossem sessões Codex.

## Publicação e evidências privadas

O [resumo público revisado](validation/public/README.md) descreve o resultado e os
limites da validação. Registros originais de conta, fatos financeiros, cliente e
sessões ficam somente na instalação local. Os links para esses artefatos e para
o texto histórico privado são referências locais e não estarão disponíveis no
GitHub. Os originais não foram apagados nem substituídos por evidências fabricadas.
Nenhum workflow automático de inferência, auditoria ou deploy foi incluído.
