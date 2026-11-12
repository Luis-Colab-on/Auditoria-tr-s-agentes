> Documento histórico anterior à migração Codex Pro. Não execute comandos de API
> descritos aqui. Estado atual: [Codex Pro](codex-pro.md) e
> [validação atual](../validation/codex-migration.md). Reprovações históricas preservadas.

# Referências conferidas em 10/11/2026

Consulta web e leitura do código oficial foram possíveis pelo conector; DNS/rede do
terminal permaneceram indisponíveis. Documentação não equivale a teste real da conta.

| Fonte | Uso na implementação |
|---|---|
| [Agents SDK](https://developers.openai.com/api/docs/guides/agents/sdk) | Runtime escolhido, controlado pela aplicação |
| [Quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart) | Agent, Runner.run, chave Platform |
| [Definições de agentes](https://developers.openai.com/api/docs/guides/agents/define-agents) | function_tool, instruções, saída Pydantic |
| [Running agents](https://developers.openai.com/api/docs/guides/agents/running-agents) | Separação entre inputs, sessions e continuation IDs |
| [Observabilidade](https://developers.openai.com/api/docs/guides/agents/integrations-observability) | Tracing desativado deliberadamente |
| [SDK Python v0.24.0](https://github.com/openai/openai-agents-python/tree/v0.24.0) | Assinaturas efetivas de Model, OpenAIResponsesModel, Runner, ModelSettings e RunConfig |
| [pyproject oficial](https://github.com/openai/openai-agents-python/blob/v0.24.0/pyproject.toml) | OpenAI >=3,<4 e httpx2; Pydantic >=2.12.2,<3 |
| [uv.lock oficial](https://github.com/openai/openai-agents-python/blob/v0.24.0/uv.lock) | Fechamento transitivo usado para gerar requirements.lock |
| [Docker Compose networks](https://docs.docker.com/reference/compose-file/networks/) | Rede interna |
| [Docker gateway modes](https://docs.docker.com/engine/network/port-publishing/) | internal sozinho permite gateway; isolated remove endereço da bridge |
| [Docker 28](https://docs.docker.com/engine/release-notes/28/) | Requisito de gateway isolated |
| [wp-env](https://developer.wordpress.org/block-editor/reference-guides/packages/packages-env/) | Avaliação da alternativa existente; nenhum ambiente local a reutilizar |
| [Playwright Docker](https://playwright.dev/docs/docker) | Pacote separado, versões combinadas, usuário/sandbox |
| [Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels) | Integração privada futura e permissões |
| [Custom MCP](https://developers.openai.com/api/docs/guides/custom-mcp-server) | Autorização ChatGPT separada da Platform |

As referências de Codex non-interactive/SDK/subagents não foram usadas como backend:
não há integração Codex CLI nesta aplicação. Portanto não se pressupõem flags ou
comandos antigos do Codex; nenhum token de sua sessão foi inspecionado.

Versões locais efetivamente instaladas: Python 3.12.3, Pydantic 2.13.4, pytest 9.1.1,
setuptools 78.1.0. A disponibilidade de modelos da conta só poderá ser verificada por
`doctor --probe-api` com uma chave própria da Platform. `gpt-6-luna` é um padrão
configurável, não uma afirmação de disponibilidade ou preço para esta conta.
