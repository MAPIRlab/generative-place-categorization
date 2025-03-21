# Paths
SEMANTIC_MAPS_FOLDER_PATH = "data/semantic_maps/"
RESULTS_FOLDER_PATH = "results/"
CLUSTERINGS_FOLDER_PATH = "data/clusterings/"
LLM_CACHE_FILE_PATH = "results/llm_cache.json"

# METHODS

# Word embeddings
METHOD_GEOMETRIC = "geometric"
METHOD_BERT = "bert"
METHOD_OPENAI = "openai"
METHOD_ROBERTA = "roberta"

# Contextualized sentence embeddings
METHOD_DEEPSEEK_SBERT = "deepseek+sbert"
METHOD_DEEPSEEK_OPENAI = "deepseek+openai"

# Word embeddings + Cluster post-processing
METHOD_BERT_POST = "bert+post"

# Contextualized sentence embeddings + Cluster post-processing
METHOD_DEEPSEEK_SBERT_POST = "deepseek+sbert+post"

# SEMANTIC DESCRIPTORS
SEMANTIC_DESCRIPTOR_ALL = "all"
SEMANTIC_DESCRIPTOR_BERT = "bert"
SEMANTIC_DESCRIPTOR_ROBERTA = "roberta"
SEMANTIC_DESCRIPTOR_OPENAI = "openai"
SEMANTIC_DESCRIPTOR_DEEPSEEK_SBERT = "deepseek+sbert"
SEMANTIC_DESCRIPTOR_DEEPSEEK_OPENAI = "deepseek+openai"
