> Documento histórico anterior à migração Codex Pro. Não execute comandos de API
> descritos aqui. Estado atual: [Codex Pro](codex-pro.md) e
> [validação atual](../validation/codex-migration.md). Reprovações históricas preservadas.

# Validação efetiva desta entrega

**Implementado, integração real ainda não validada.** Não declarar o sistema
operacional com três agentes antes de executar os testes reais abaixo.

Ambiente observado em 10/11/2026: Ubuntu 24.04.3, WSL2, Python 3.12.3, Git 2.43.0,
aproximadamente 7,8 GB RAM e 911 GB livres. Diretório inicial vazio, sem AGENTS.md
aplicável encontrado nos ancestrais/projeto. Nenhuma fonte FAEPA foi analisada ou alterada.

## Resultados reais

**Última rodada: 5 aprovados, 2 falhos e 1 não executado**, em
`20261110T190043Z-cc9824bc`. Os novos logs mostram `OOMKilled=true` no MySQL dos
dois ambientes, com limite de 512 MiB. As verificações PHP/browser não chegaram a
executar; os testes pytest falharam pela falta de ambiente pronto. A configuração
de logging corrigida funcionou. O limite do banco foi ajustado para 1 GiB, mantendo
os outros serviços em 512 MiB e os demais controles. **47 verificações de
infraestrutura passaram**; a confirmação desse ajuste no Docker ainda está pendente.
API desautorizada; nenhum consumo de API nesta etapa.
[Resultados, limites e evidências](validacao-bootstrap.md).

Após a alteração do perfil, a suíte offline completa foi executada com
`AUDIT3_LIVE_TEST=0 .venv/bin/python -m pytest -q -m 'not docker and not live'`:
**111 aprovados, zero falhas, 8 desmarcados**, em 14,58 s.
[JUnit](../validation/offline-memory-fix-regression.xml). Os oito casos de integração
foram excluídos deliberadamente dessa suíte; ela não substitui a execução no WSL.

**Histórico — 5 aprovados, 2 falhos e 1 não executado**, em
`20261110T181218Z-ebf02c03`. O isolamento genérico passou em Docker com todos os
marcadores esperados. Os dois casos Compose foram bloqueados pela inspeção de segurança
antes de executar PHP/browser; não eram mais imagens ausentes. Foi corrigida a declaração
dos mounts para exigir Mount API e preservar a proibição de `HostConfig.Binds`.
**36 verificações de infraestrutura passaram**. A inspeção dos mounts foi confirmada
na rodada seguinte, `20261110T184915Z-9e6b88f9`.
[Diagnóstico, limites e evidências](validacao-compose.md).

**Rodada anterior — execução WSL recebida e correção do teste:** a sessão
`20261110T175257Z-b27f80b7` registrou **4 aprovados, 1 falho, 3 não executados**.
A falha de isolamento foi uma `PermissionError` não tratada na consulta a `/root/.ssh`;
as verificações seguintes de escrita/rede não foram alcançadas. A correção fica somente
no teste e distingue caminho ausente de acesso negado, mantendo falha para caminho
visível e demais erros. **21 regressões/verificações unitárias passaram**. A tentativa
Docker após a correção ficou bloqueada nesta sessão; a rodada WSL
`20261110T181218Z-ebf02c03` confirmou posteriormente todos os probes de isolamento.
A imagem de navegador foi construída pelo usuário após o resultado antigo. **API
desautorizada** nesta etapa. [Investigação e evidências completas](validacao-isolamento.md).

Após a instalação de Docker pelo usuário, às 17:41 UTC de 10/11/2026: Docker
29.9.3, Compose 5.7.0 e socket visíveis; acesso ao servidor negado (`EPERM`) no
processo restrito. Os oito testes foram tentados novamente devido à mudança de
ambiente: **0 aprovados, 0 falhas, 8 não executados**. Sete estão bloqueados no acesso
ao daemon; o teste de API também encontra chave/runtime ausentes e rede restrita.
Nenhuma chamada de modelo nem container de teste foi executado.
[Novo relatório](../validation/20261110T174224Z-1ef5b9ed/report.md).
O [diagnóstico do terminal WSL normal](../validation/host-docker-diagnostic.json),
salvo pelo usuário às 17:46 UTC, confirmou servidor Docker 29.9.3 e Compose 5.7.0
acessíveis, com DNS/HTTPS funcionando. Portanto, o acesso negado observado nesta
sessão não representa falha do daemon no WSL. Naquele momento, imagens e testes nesse
terminal ainda não tinham sido verificados. Nenhum teste foi promovido a aprovado
só por esse diagnóstico.

Atualização da continuação em 10/11/2026:

Comando: `.venv/bin/python -m pytest -q --junitxml=validation/pytest-followup.xml`

**78 testes aprovados, 8 não executados (skips), zero falhas**.
O [JUnit atualizado](../validation/pytest-followup.xml)
registra a execução efetiva. São testes offline de infraestrutura, incluindo mocks
explicitamente identificados; não são evidência de precisão dos modelos nem de
isolamento do Docker em funcionamento.

Os oito testes pendentes também foram selecionados explicitamente com o novo
`scripts/validate_pending.py --api --model gpt-6-luna --budget-usd 5 --max-calls 48`:
**0 aprovados, 0 falhas, 8 não executados** por pré-requisitos ausentes. Nenhuma chamada
de modelo ou execução Docker ocorreu. O nome do modelo configurado não comprova
disponibilidade na conta. [Relatório por teste](../validation/20261110T173630Z-fd2722f8/report.md)
e [dados estruturados](../validation/20261110T173630Z-fd2722f8/results.json).
A execução anterior do novo comando também foi preservada; a repetição validou
alterações na sanitização/registro, sem consumo de API. O resultado original de
67 aprovados/8 skips permanece em [pytest.xml](../validation/pytest.xml).

Foram acrescentadas verificações de diagnóstico sem segredo, bloqueio de socket antes
do DNS, ausência de retries financeiros, limites monetários finitos, conversão honesta
de skips/JUnit ausente e rejeição de mocks/baseline não executada no critério real.
O wheel atualizado foi construído e teve módulos/assets conferidos; seu checksum está
no [registro de build](../validation/20261110T173630Z-fd2722f8/build/result.json).
`pip check` aprovou o ambiente efetivamente instalado (core/dev); isso não valida as
dependências de runtime ausentes. [Resumo da continuação](../validation/followup-summary.json).

Também foram executados:

- Instalação do controlador editável e do lock de desenvolvimento usando wheels do
  cache local; `pip check` sem dependências quebradas no ambiente instalado.
- Construção do [wheel instalável](../validation/audit3-0.1.0-py3-none-any.whl),
  com conferência da inclusão dos módulos, prompts, perfis e assets necessários.
- Compilação Python do código do controlador e validação dos três perfis/configuração
  e schemas de saída Pydantic.
- `audit3 doctor --probe-api`: [resultado](../validation/doctor.json), sem imprimir credenciais.
- CLI sobre ZIP da fixture `bug`: prepare, run, status, report e export. `run` terminou
  **partial/inconclusivo**, registrando Docker indisponível e chave ausente.
  Nenhuma chamada de modelo ou execução Docker ocorreu nessa demonstração.
- [Registro da CLI](../validation/cli-smoke.json), [relatório gerado](../validation/offline-smoke.md)
  e [exportação ZIP](../validation/offline-smoke.zip). Não são uma auditoria real da fixture.

Durante o desenvolvimento, uma coleta inicial do pytest tentou importar testes das
fixtures e falhou antes de executá-los, por ausência dos módulos da fixture no host.
A coleta foi corrigida para excluir `tests/fixtures` explicitamente. Os testes dessas
fontes só são executáveis pelo executor isolado; nenhum resultado de fixture no host
foi contado como validação. Uma advertência intencional de ZIP duplicado foi capturada
pelo teste correspondente, sem enfraquecer sua rejeição.

## O que os testes aprovados cobrem

| Área | Evidência offline |
|---|---|
| Snapshot | Commit explícito, SHA completo, working tree suja preservada, ZIP sem commit, inventário/exclusões |
| Caminhos | Traversal, caminho absoluto, Windows/ADS, symlink, nomes reservados, colisão e ZIP bomb |
| Integridade | Fonte alterada, HMAC alterado, troca de namespace, congelamento e lock de execução |
| Ferramentas | Identidade não selecionável, intervalos realmente devolvidos, truncamento, referência não lida |
| Barreiras | Parecer/evidência de outro papel e narrativa antiga recusados antes da publicação |
| Evidência | Receipt inexistente, versão errada, teste não executado e alegação de origem sem comparação rejeitados |
| Papéis | Inputs separados com mocks, inspeção cega, contestação, réplica e achados do Defensor |
| Juiz | Uma rodada adicional por novo achado; descoberta final fica pendente |
| Decisões | Hipótese não impõe correção; mecanismos diferentes no mesmo arquivo não são fundidos |
| Métricas | Duplicatas/causas distintas; 16 asserções não viram 16 bugs; precisão/recall dependem de mapeamento revisado |
| Limites | JSON inválido limitado, orçamento/reserva, uso desconhecido, timeout total e saída limitada |
| Recuperação | Cancelamento antes/durante execução, retomada de checkpoint e limite de tentativa interrompida |
| Executor | argv fixo, proibição de shell de host, validação de inspeção Docker e Compose, estado bloqueado honesto |
| Exportação | Checksums, seleção de evidência, ausência da chave de integridade e canário de credencial |

O README malicioso permanece na fixture e não modifica as permissões. Isso testa
controles do motor, não comprova que modelos reais jamais seguirão uma instrução
maliciosa em seu parecer.

## Bloqueios observados

1. Após a instalação, Docker/Compose estão disponíveis e o servidor foi confirmado
   no terminal WSL normal. A sessão Codex permanece sem permissão de conexão ao
   socket. Sete testes dependem de Docker; o oitavo, de Docker **e API**. É necessário
   iniciar os testes no terminal WSL e analisar os resultados salvos no projeto.
2. `OPENAI_API_KEY` não está configurada. Não se leu token do ChatGPT nem se pediu
   segredo no chat. Disponibilidade dos modelos e permissões da conta não verificadas.
3. A investigação comparativa demonstrou **negação de socket no processo restrito,
   antes de DNS**. No terminal WSL do usuário, API/PyPI resolvem e respondem HTTPS
   (401 sem chave e 200, respectivamente). Nenhuma configuração de rede foi alterada.
   [Diagnósticos, dependências e instruções locais](concluir-validacao.md).
   `openai-agents`/`openai` não estão instalados no venv; a integração foi conferida
   contra assinaturas do código oficial v0.24.0, mas ainda não importada/executada
   com a distribuição instalada. O lock completo deriva do lock oficial com overrides
   Pydantic compatíveis; sua instalação completa precisa ser confirmada com rede.
4. Sem execução real, precisão, falsos positivos e defeitos conhecidos omitidos por
   modelos são **desconhecidos**. Não há custo de auditoria observado. O número de
   chamadas da API do motor nesta tarefa é zero; isso não é uma estimativa de custo futuro.

Os 78 testes aprovados não removem nenhum desses bloqueios.

## Teste real reproduzível quando houver ambiente e orçamento

Siga o [procedimento local completo](concluir-validacao.md), incluindo instalação do
runtime, imagens, chave oculta e limite financeiro na Platform. O comando novo exige
modelo explícito e salva os artefatos em diretório único, sem apagar tentativas anteriores.

```bash
python scripts/validate_pending.py --api --model MODELO_DISPONIVEL \
  --budget-usd 5 --call-reserve-usd 0.10 --max-calls 48 --total-seconds 900
```

O teste real usa a fixture `clean` e exige baseline Docker aprovada antes de chamar
API, chamadas concluídas dos três papéis, contextos separados, ferramentas, barreira,
contestação/réplica, julgamento e cobertura sem lacunas. Não permite apresentar uma
análise estática parcial como validação completa. Precisão e recall permanecem
indefinidos quando seus denominadores são zero; a fixture correta não mede recall.

Para avaliar qualidade além do smoke, prepare separadamente `bug`, `layered`, `rare`,
`partial` e as duas versões; não inclua `tests/expectations.json` no snapshot. Revise
o mecanismo de cada achado comprovado e produza `{finding_id: known_defect_id}` ou
`null` para falso positivo. Use:

```bash
python scripts/evaluate_fixture.py --report report.json --fixture bug --mapping mapping.json
```

O cálculo informa precisão por mecanismo, falsos positivos, recall, defeitos omitidos,
duplicatas e lacunas. Não se avalia qualidade somente pelo número de achados. Nenhuma
métrica de qualidade de modelos reais foi fabricada nesta entrega.

## Limitações e opções futuras

MCP com fila, autorização por execução e idempotência está documentado, não implementado
nem publicado. Download privado GitHub, materialização automática de LFS/submódulos,
coleta genérica de screenshots/artefatos binários, matriz Windows real, simuladores
comerciais completos e validação de plugins ausentes ficam fora deste MVP. O perfil
FAEPA é configurável e ainda não validado contra o plugin. Retomadas não persistem
histórico bruto de reasoning: reconstroem contexto de observações estruturadas próprias.
