# audit3

**Restrição financeira permanente:** [nenhum gasto adicional está autorizado](AGENTS.md).
Somente a franquia da assinatura existente da empresa; créditos adicionais, recarga,
mudanças de assinatura e alternativas pagas são proibidos. A regra não expira.
Fatos financeiros vencidos ou desconhecidos bloqueiam inferência.

Auditor, Defensor e Juiz em três sessões distintas do **Codex oficial**, controlados
por Python. Modelo solicitado nos três papéis: `gpt-6-astra`, Max (`max`), Standard
(`default`). Extra High (`xhigh`) só é selecionado se Max não constar do catálogo.
Não há gerente modelo, subdelegação, Fast, Ultrafast ou fallback pago.

**Validação sintética PHP/WordPress encerrada e aprovada sob extensão autorizada.**
O run `570af15e2192e19f73ddaff7` concluiu os três papéis e passou nas 22 checagens
com até 300 segundos por turno e extensão excepcional do teto global de 900 para
1.500 segundos, restrita ao julgamento final. Totais: 11/16 chamadas e 1.009,27
segundos acumulados. Não houve novo run, repetição de fases concluídas ou slots extras.

O estado bruto `partial` foi preservado. A revisão local prevista das 66 mensagens
de limitação concluiu o escopo como `completed`, sem nova inferência nem alteração
dos pareceres. A reprovação histórica sob 900 segundos permanece intacta. A
aprovação vale para a fixture e os controles demonstrados; não é validação de um
projeto real ou de produção. FAEPA permanece fora do escopo.

Consulte o **[guia de uso da versão validada](docs/uso-versao-validada.md)** para
preparação local, delimitação de escopo, comandos exatos, conferência financeira,
início, acompanhamento, retomada, limites, resultados e limitações. Os
[resultados consolidados](validation/php-wordpress-final-extension-20261112/result-summary.json),
[a aceitação](validation/php-wordpress-final-extension-20261112/acceptance.json) e
[o julgamento original](validation/php-wordpress-final-extension-20261112/original-final-judgment.json)
são a referência encerrada; não repetir seus roteiros de execução.

A infraestrutura WSL aprovada em `20261110T210248Z-0d1e3ccb` e o histórico Python
encerrado foram preservados. O [texto anterior de status](docs/historico-status-readme-20261112.md)
foi arquivado com suas referências, sem apagar falhas ou evidências anteriores.

## Instalação

Python 3.12 é o alvo testado (pacote admite 3.11+). Instale o **Codex CLI 0.167.0**
pelo mecanismo oficial. O contrato experimental é fixado nessa versão. O projeto
não instala SDK de inferência, Agents SDK ou segunda linguagem.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.lock
.venv/bin/python -m pip install --no-build-isolation --no-deps -e .
.venv/bin/python -m pytest -q -m 'not docker and not live'
.venv/bin/audit3 doctor
.venv/bin/audit3 codex-setup
```

Execute o comando de login mostrado por `codex-setup` no terminal normal: ele usa
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
- [Resultado aprovado PHP/WordPress](validation/php-wordpress-final-extension-20261112/result-summary.json)
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
