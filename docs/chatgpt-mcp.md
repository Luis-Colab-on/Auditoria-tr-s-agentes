# Uso pelo ChatGPT e MCP opcional

O caminho funcional do MVP é `audit3 export ID --output resultado.zip`. Anexe o ZIP
ou o Markdown/JSON extraído a uma conversa. O ChatGPT pode interpretar decisões e
receipts; não deve alegar que ele próprio realizou testes ou que três perspectivas
na conversa equivalem às três investigações do motor externo. Leia `validation`,
`runtime_mode`, estado operacional, barreira, usage e tipos de execução nos receipts.

Um servidor MCP é etapa **opcional futura**, não publicado/instalado nesta entrega.
Ele reutilizaria o mesmo `prepare`, `Workflow`, `Store` e exportação. Não usaria Codex
como backend. Conectar Codex como cliente a MCP e expor este motor como servidor são
operações diferentes. Não há dependência do comando removido `codex mcp-server`.

Contrato proposto:

| Ferramenta | Entrada | Resultado |
|---|---|---|
| start_audit | project_id, ref, profile, idempotency_key | run_id imediato |
| get_audit_status | run_id | fase, estado, orçamento e lacunas |
| get_audit_report | run_id | relatório estruturado/legível |
| get_evidence | run_id, evidence_id | receipt permitido e artefatos selecionados |
| cancel_audit | run_id | cancel_requested |

O servidor aceitaria apenas projetos previamente cadastrados pelo operador (exemplo
em `examples/projects.json`), com caminho local fixado ou URL permitida, refs/perfis
autorizados e identidade do usuário. Nunca aceitaria shell, argv arbitrário ou caminho
remoto arbitrário. A autorização por execução deve vincular usuário, projeto, ref
resolvida, perfil, orçamento e envio de código à API.

`start_audit` validaria autorização, faria reserva idempotente atômica por
`(usuário, project_id, idempotency_key)` e retornaria rapidamente. Um worker local
executaria a auditoria fora da requisição MCP. Retries com a mesma chave e parâmetros
retornariam o mesmo run_id; parâmetros diferentes com mesma chave seriam conflito.
O lock do motor evita controladores duplicados, mas não substitui a implementação
dessa fila/autorização/idempotência do adaptador futuro. Dados de um usuário não
seriam expostos a outro; evidências privadas continuariam submetidas às barreiras.

As permissões de custom MCP no ChatGPT e as permissões da organização Platform são
separadas. Nesta sessão não existe ferramenta autorizada para confirmar permissões
de custom MCP/túneis da conta; chave de API também está ausente. A documentação foi
conferida, mas disponibilidade para esta conta permanece **não verificada**.

O [Secure MCP Tunnel oficial](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
é uma alternativa para um servidor privado quando habilitado. Exige tunnel_id, chave
de runtime e permissões Platform: Read+Manage para criar/editar e Read+Use para executar;
o workspace ChatGPT precisa permitir o servidor customizado. O cliente inicia conexão
HTTPS de saída, sem publicar um listener de entrada. Isso não autoriza instalar um
túnel automaticamente. Nenhum servidor, túnel ou conta externa foi criado aqui.

Até confirmar acesso e implementar o adaptador com autorização/idempotência, mantenha
a exportação manual. Veja também a documentação oficial de
[custom MCP](https://developers.openai.com/api/docs/guides/custom-mcp-server).
