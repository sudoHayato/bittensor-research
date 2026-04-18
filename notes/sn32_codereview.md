=== SUBNET 32 — ItsAI ===
Tipo: AI-detection / Binary text classification (human vs AI-generated)
Status: active (v3.14.0, last commit merged PR #87, steady development since 2024-03)
Registration cost: 0.5 TAO (500,000 rao)
Hardware minimo realista: GPU com 16-24 GB VRAM (RTX A4000 minimo, RTX 4090 recomendado). Miner usa DeBERTa-v3-large para classificacao. Validator precisa A100 80GB + Ollama a correr 30+ LLMs ate 123B parametros.
Custo Hetzner equivalente: ~179 EUR/mes (GEX44-OK para miner; validator = ENTERPRISE-ONLY, precisa A100 80GB)
Tarefa: Mineiros recebem textos (humanos do Pile + gerados por 30+ LLMs via Ollama) e devem classificar cada palavra como humana ou AI.
         Recompensa = media de F1-score + FP-score + AP-score, com penalidades por inconsistencia e domain robustness.
Competitividade: top1=0.535 TAO/dia, top10=0.501 TAO/dia, mediana=0.402 TAO/dia, Gini=0.54, 156/248 miners activos
Distribuicao on-chain vs off-chain: match parcial — leaderboard HuggingFace (https://huggingface.co/spaces/sergak0/ai-detection-leaderboard) dinamico (JS-rendered, nao scrapeavel directamente). WandB em https://wandb.ai/itsai-dev/subnet32 com dados assinados por hotkey do validator. Sem discrepancia detectavel mas leaderboard opaco por ser client-side.
Receita por miner mediano: 0.40 TAO/dia (12.04 TAO/mes = ~3,613 EUR/mes at TAO=$300)
Break-even: 0.05 meses (~1.5 dias)
Immunity period: 7200 blocks (~24 horas)
Risco deregistration: LOW — immunity 24h e basta o modelo base funcional para receber score > 0. Registration cost de apenas 0.5 TAO. Distribuicao relativamente plana entre miners activos (Gini 0.54).
Discord/Docs quality: MED — Discord e o geral do Bittensor (https://discord.gg/bittensor), sem server dedicado. FAQ util em docs/FAQ.md. Mining/validating docs claros mas basicos. Notion FAQ externo referenciado.
Burn capture detectado: NO — nenhum padrao BURN_LIST, TEAM_UID, FOUNDER_UID, TREASURY_HOTKEY ou weight bias detectado no codigo.
Centralizacao: MED — 8 validators apenas, top validator (UID 31, owner key) recebe ~25x mais que top miner. Validators controlam scoring integralmente com commit_reveal_weights habilitado. Porem, entre miners a distribuicao e razoavelmente plana.
Off-chain scoring: transparente/parcial — WandB logging com assinatura criptografica do validator hotkey. Leaderboard HuggingFace existe mas e JS-rendered. Reward formula esta totalmente no codigo aberto (reward.py).
Red flags:
  1. trust_remote_code=True em ppl_model.py (L18) — o modelo PPL e carregado com trust_remote_code=True no AutoTokenizer, permitindo execucao de codigo arbitrario se o modelo HuggingFace for comprometido.
  2. parse_versions() em neuron.py (L204) faz HTTP GET a raw.githubusercontent.com para obter __version__ e __least_acceptable_version__ — se o repo GitHub for comprometido, pode forcar miners/validators a aceitar versoes maliciosas ou bloquear versoes legitimas.
  3. Auto-updater (scripts/start_validator.py + run.sh) faz git pull --rebase automaticamente sem verificacao de assinatura de commits — supply chain risk se repo for comprometido.
  4. Validator precisa correr 30+ LLMs via Ollama (ate 123B params) — barreira de entrada muito alta, centralizando validacao em poucos operadores.
  5. min_alpha_amount default=0 — qualquer coldkey pode minar sem stake minimo de alpha, facilitando sybil attacks.
Sample snippets:

1) trust_remote_code risk (neurons/miners/ppl_model.py:18):
```python
self.tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
```

2) Remote version fetching sem verificacao (detection/base/neuron.py:200-220):
```python
def parse_versions(self):
    self.version = "10.0.0"
    self.least_acceptable_version = "0.0.0"
    response = requests.get(version_url)
    if response.status_code == 200:
        content = response.text
        version = re.search(version_pattern, content).group(1)
        least_acceptable_version = re.search(least_acceptable_version_pattern, content).group(1)
        self.version = version
        self.least_acceptable_version = least_acceptable_version
```

3) Softmax temperature=100 amplification on rewards (detection/validator/forward.py:209-211):
```python
m = torch.nn.Softmax()
rewards_tensor = m(rewards_tensor * 100)
```
Este multiplicador de temperatura de 100 amplifica dramaticamente diferencas minimas de score, criando winner-take-most dynamics apesar da distribuicao parecer plana.

Veredicto: GO — Receita/custo excepcional (break-even ~1.5 dias), codigo aberto limpo sem burn capture, tarefa com valor real de mercado (AI detection), equipa activa com empresa registada. Riscos sao menores (supply chain, trust_remote_code) e comuns no ecossistema.
