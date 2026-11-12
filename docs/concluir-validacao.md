# Concluir a validação no terminal normal WSL

A migração Codex está em [Codex Pro](codex-pro.md); resultados em
[relatório atual](../validation/codex-migration.md). Os antigos passos de API foram
retirados. `--api` e `doctor --probe-api` falham antes de chamadas.

Primeiro execute as verificações Docker com as imagens já existentes:

```bash
.venv/bin/python scripts/validate_pending.py
```

Não é necessário reconstruir `audit3-wordpress:local` ou `audit3-browser:local` para
esta migração. Neste processo restrito, o socket Docker retorna permissão negada.
As duas falhas PHP/browser anteriores permanecem reprovadas até nova execução real.
O novo relatório preserva logs de inicialização e falha de SMTP para diagnóstico.

Para o smoke Codex, prepare login específico com `audit3 codex-setup`, execute o
comando oficial mostrado e consulte `audit3 doctor --probe-codex`. A confirmação
factual de recarga automática desativada e ausência de créditos extras precisa vir
do painel oficial. Não forneça credenciais. Depois use o comando `--codex` descrito
em [Codex Pro](codex-pro.md). Sem esses fatos, deixe somente o smoke bloqueado.
