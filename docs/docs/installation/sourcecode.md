# Source Code Deployment

## Environmental requirements

| Startup Mode         | CPU * MEM    |       GPU      |         Remark  |
|:--------------------:|:------------:|:--------------:|:---------------:|
|     Proxy model          |    4C * 8G      |        None    |  Proxy model does not rely on GPU                         |
|     Local model          |    8C * 32G     |       24G      |  It is best to start locally with a GPU of 24G or above   |


## Environment Preparation

### Download Source Code

:::tip
Download derisk 
:::

```bash
git clone https://github.com/derisk-ai/derisk.git
```

:::info note
There are some ways to install uv:
:::

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

<Tabs
  defaultValue="uv_sh"
  values={[
    {label: 'Command (macOS And Linux)', value: 'uv_sh'},
    {label: 'PyPI', value: 'uv_pypi'},
    {label: 'Other', value: 'uv_other'},
  ]}>
  <TabItem value="uv_sh" label="Command">
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
  </TabItem>

  <TabItem value="uv_pypi" label="Pypi">
Install uv using pipx.

```bash
python -m pip install --upgrade pip
python -m pip install --upgrade pipx
python -m pipx ensurepath
pipx install uv --global
```
  </TabItem>

  <TabItem value="uv_other" label="Other">

You can see more installation methods on the [uv installation](https://docs.astral.sh/uv/getting-started/installation/)
  </TabItem>

</Tabs>

Then, you can run `uv --version` to check if uv is installed successfully.

```bash
uv --version
```

## Deploy derisk 

### Install Dependencies

<Tabs
  defaultValue="openai"
  values={[
    {label: 'DeepSeek (proxy)', value: 'deepseek'},
    {label: 'QwQ (local)', value: 'QwQ-32B'},
    {label: 'OpenAI (proxy)', value: 'openai'},
  ]}>

 
<TabItem value="deepseek" label="DeepSeek(proxy)">

```bash
# Use uv to install dependencies needed for OpenAI proxy
uv sync --all-packages \
--extra "base" \
--extra "proxy_openai" \
--extra "rag" \
--extra "storage_chromadb" \
```

### Run Webserver

To run derisk with DeepSeek proxy, you must provide the DeepSeek API key in the `configs/derisk-proxy-deepseek.toml`.

And you can specify your embedding model in the `configs/derisk-proxy-deepseek.toml` configuration file, the default embedding model is `BAAI/bge-large-zh-v1.5`. If you want to use other embedding models, you can modify the `configs/derisk-proxy-deepseek.toml` configuration file and specify the `name` and `provider` of the embedding model in the `[[models.embeddings]]` section. The provider can be `hf`.

```toml
# Model Configurations
[models]
[[models.llms]]
# name = "deepseek-chat"
name = "deepseek-reasoner"
provider = "proxy/deepseek"
api_key = "your-deepseek-api-key"
[[models.embeddings]]
name = "BAAI/bge-large-zh-v1.5"
provider = "hf"
# If not provided, the model will be downloaded from the Hugging Face model hub
# uncomment the following line to specify the model path in the local file system
# path = "the-model-path-in-the-local-file-system"
path = "/data/models/bge-large-zh-v1.5"
```

Then run the following command to start the webserver:

```bash
uv run derisk start webserver --config configs/derisk-proxy-deepseek.toml
```
In the above command, `--config` specifies the configuration file, and `configs/derisk-proxy-deepseek.toml` is the configuration file for the DeepSeek proxy model, you can also use other configuration files or create your own configuration file according to your needs.

Optionally, you can also use the following command to start the webserver:
```bash
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-deepseek.toml
```

  </TabItem>

 <TabItem value="openai" label="OpenAI(proxy)">

```bash
# Use uv to install dependencies needed for OpenAI proxy
uv sync --all-packages \
--extra "base" \
--extra "proxy_openai" \
--extra "rag" \
--extra "storage_chromadb" \
```

### Run Webserver

To run derisk with OpenAI proxy, you must provide the OpenAI API key in the `configs/derisk-proxy-openai.toml` configuration file.

```toml
# Model Configurations
[models]
[[models.llms]]
...
api_key = "your-deepseek-api-key"
[[models.embeddings]]
...
api_key = "your-deepseek-api-key"
```

Then run the following command to start the webserver:

```bash
uv run derisk start webserver --config configs/derisk-proxy-deepseek.toml
```
In the above command, `--config` specifies the configuration file, and `configs/derisk-proxy-deepseek.toml` is the configuration file for the DeepSeek proxy model, you can also use other configuration files or create your own configuration file according to your needs.

Optionally, you can also use the following command to start the webserver:
```bash
uv run python packages/derisk-app/src/derisk_app/derisk_server.py --config configs/derisk-proxy-deepseek.toml
```

  </TabItem>

  <TabItem value="QwQ-32B" label="qwq-32B(local)">

```bash
# Use uv to install dependencies needed for GLM4
# Install core dependencies and select desired extensions
uv sync --all-packages \
--extra "base" \
--extra "cuda121" \
--extra "hf" \
--extra "rag" \
--extra "storage_chromadb" \
--extra "quant_bnb" 
```

### Run Webserver

To run derisk with the local model. You can modify the `configs/derisk-local-glm.toml` configuration file to specify the model path and other parameters.

```toml
# Model Configurations
[models]
[[models.llms]]
name = "Qwen/QwQ-32B"
provider = "hf"
# If not provided, the model will be downloaded from the Hugging Face model hub
# uncomment the following line to specify the model path in the local file system
# path = "the-model-path-in-the-local-file-system"

[[models.embeddings]]
name = "BAAI/bge-large-zh-v1.5"
provider = "hf"
# If not provided, the model will be downloaded from the Hugging Face model hub
# uncomment the following line to specify the model path in the local file system
# path = "the-model-path-in-the-local-file-system"
```
In the above configuration file, `[[models.llms]]` specifies the LLM model, and `[[models.embeddings]]` specifies the embedding model. If you not provide the `path` parameter, the model will be downloaded from the Hugging Face model hub according to the `name` parameter.

Then run the following command to start the webserver:

```bash
uv run derisk start webserver --config configs/derisk-local-glm.toml
```

  </TabItem>
</Tabs>


## Visit Website

Open your browser and visit [`http://localhost:7777`](http://localhost:7777)

### (Optional) Run Web Front-end Separately

You can also run the web front-end separately:

```bash
cd web && npm install
cp .env.template .env
// Set API_BASE_URL to your derisk server address, usually http://localhost:7777
npm run dev
```
Open your browser and visit [`http://localhost:3000`](http://localhost:3000)


## Install derisk Application Database
<Tabs
  defaultValue="sqlite"
  values={[
    {label: 'SQLite', value: 'sqlite'},
    {label: 'MySQL', value: 'mysql'},
  ]}>
<TabItem value="sqlite" label="sqlite">

:::tip NOTE

You do not need to separately create the database tables related to the derisk application in SQLite; 
they will be created automatically for you by default.

:::

Modify your toml configuration file to use SQLite as the database(Is the default setting).
```toml
[service.web.database]
type = "sqlite"
path = "pilot/meta_data/derisk.db"
```


 </TabItem>
<TabItem value="mysql" label="MySQL">

1. Frist, execute MySQL script to create database and tables.

```bash
$ mysql -h127.0.0.1 -uroot -p{your_password} < ./assets/schema/derisk.sql
```

2. Second, modify your toml configuration file to use MySQL as the database.

```toml
[service.web.database]
type = "mysql"
host = "127.0.0.1"
port = 3306
user = "root"
database = "derisk"
password = "aa123456"
```
Please replace the `host`, `port`, `user`, `database`, and `password` with your own MySQL database settings.

 </TabItem>
</Tabs>


## Test data (optional)
The derisk project has a part of test data built-in by default, which can be loaded into the local database for testing through the following command
- **Linux**

```bash
bash ./scripts/examples/load_examples.sh

```
- **Windows**

```bash
.\scripts\examples\load_examples.bat
```

:::

## Visit website
Open the browser and visit [`http://localhost:7777`](http://localhost:7777)