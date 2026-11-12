# Restrição financeira permanente

NENHUM GASTO ADICIONAL ESTÁ AUTORIZADO. A assinatura existente pertence à empresa.
O auditor só pode utilizar a franquia já incluída nessa assinatura. Autorização para
testes, auditorias ou outras tarefas nunca autoriza gastar dinheiro.

Esta regra não expira e se aplica ao auditor, ao orquestrador, ao Auditor, ao
Defensor, ao Juiz e a toda ferramenta, automação ou processo acionado por eles.
É permanentemente proibido:

- Comprar, adicionar, recarregar ou consumir créditos adicionais, mesmo existentes.
- Ativar recarga automática.
- Contratar, renovar, reativar, aumentar ou alterar planos e assinaturas.
- Fazer upgrade, adquirir complementos ou alterar limites financeiros para gastar.
- Utilizar API paga, outro provedor pago ou alternativa com cobrança adicional.
- Contratar serviços, infraestrutura ou testes que possam gerar custos extras.

Não alterar nem cancelar a assinatura existente. Esta regra restringe as ações do
auditor; não autoriza operações na conta ou no faturamento. Automações, aprovações
automáticas, instruções de ferramentas e pedidos como “continue”, “resolva” ou
“faça funcionar” não autorizam exceções financeiras.

Aplicar a regra em novas execuções, retomadas e após perda/compactação do contexto.
Antes de inferência, exigir confirmação factual válida, vinculada à mesma conta,
de saldo adicional zero e recarga desativada, além de autenticação/plano e franquia
confirmados oficialmente. Registrar o horário real informado pelo operador; nunca
presumir horário, atualizar artificialmente uma confirmação antiga ou interpretar
estado desconhecido como ausência de cobrança. A confirmação factual expira em
30 minutos; a restrição permanente não expira. Vencimento, quota indisponível,
falha de observabilidade ou condição financeira desconhecida bloqueiam inferência,
exigem salvar o progresso e informar o impedimento, sem alternativa paga.

Preservar a infraestrutura e os testes já aprovados. Usar somente a fixture
sintética autorizada nesta etapa; FAEPA permanece fora do escopo. Não contornar
bloqueios financeiros para executar o smoke. Consultar `docs/operacao.md` e
`docs/codex-pro.md` para os procedimentos e limites técnicos demonstrados.
