import { ChatContext } from '@/app/chat-context';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import { Button, Card, Form, Input, Spin } from 'antd';
import dynamic from 'next/dynamic';
import React, { useContext } from 'react';
import { useTranslation } from 'react-i18next';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { dark, docco } from 'react-syntax-highlighter/dist/esm/styles/prism';

const MarkdownContext = dynamic(() => import('@/new-components/common/MarkdownContext'), { ssr: false });

const aaa = `<div class="markdown-body entry-content container-lg" itemprop="text"><div class="markdown-heading" dir="auto"><h1 class="heading-element" dir="auto">21st.dev Magic AI Agent</h1><a id="user-content-21stdev-magic-ai-agent" class="anchor" aria-label="Permalink: 21st.dev Magic AI Agent" href="#21stdev-magic-ai-agent"></a></div>
<p dir="auto"><a target="_blank" rel="noopener noreferrer nofollow" href="https://camo.githubusercontent.com/def584ae0888afdd28ea5ccbe9b4bab468fecbeda70c3170868b1990c0d9d676/68747470733a2f2f323173742e6465762f6d616769632d6167656e742d6f672d696d6167652e706e67"><img src="https://camo.githubusercontent.com/def584ae0888afdd28ea5ccbe9b4bab468fecbeda70c3170868b1990c0d9d676/68747470733a2f2f323173742e6465762f6d616769632d6167656e742d6f672d696d6167652e706e67" alt="MCP Banner" data-canonical-src="https://21st.dev/magic-agent-og-image.png" style="max-width: 100%;"></a></p>
<p dir="auto">Magic Component Platform (MCP) is a powerful AI-driven tool that helps developers create beautiful, modern UI components instantly through natural language descriptions. It integrates seamlessly with popular IDEs and provides a streamlined workflow for UI development.</p>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">🌟 Features</h2><a id="user-content--features" class="anchor" aria-label="Permalink: 🌟 Features" href="#-features"></a></div>
<ul dir="auto"><li><strong>AI-Powered UI Generation</strong>: Create UI components by describing them in natural language</li><li><strong>Multi-IDE Support</strong>:<ul dir="auto">svg
<li><a href="https://cursor.com" rel="nofollow">Cursor</a> IDE integration</li>
<li><a href="https://windsurf.ai" rel="nofollow">Windsurf</a> support</li>
<li><a href="https://cline.bot" rel="nofollow">VSCode + Cline</a> integration (Beta)</li>
</ul>
</li>
<li><strong>Modern Component Library</strong>: Access to a vast collection of pre-built, customizable components inspired by <a href="https://21st.dev" rel="nofollow">21st.dev</a></li>
<li><strong>Real-time Preview</strong>: Instantly see your components as you create them</li>
<li><strong>TypeScript Support</strong>: Full TypeScript support for type-safe development</li>
<li><strong>SVGL Integration</strong>: Access to a vast collection of professional brand assets and logos</li>
<li><strong>Component Enhancement</strong>: Improve existing components with advanced features and animations (Coming Soon)</li>
</ul>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">🎯 How It Works</h2><a id="user-content--how-it-works" class="anchor" aria-label="Permalink: 🎯 How It Works" href="#-how-it-works"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<ol dir="auto">
<li>
<p dir="auto"><strong>Tell Agent What You Need</strong></p>
<ul dir="auto">
<li>In your AI Agent's chat, just type <code>/ui</code> and describe the component you're looking for</li>
<li>Example: <code>/ui create a modern navigation bar with responsive design</code></li>
</ul>
</li>
<li>
<p dir="auto"><strong>Let Magic Create It</strong></p>
<ul dir="auto">
<li>Your IDE prompts you to use Magic</li>
<li>Magic instantly builds a polished UI component</li>
<li>Components are inspired by 21st.dev's library</li>
</ul>
</li>
<li>
<p dir="auto"><strong>Seamless Integration</strong></p>
<ul dir="auto">
<li>Components are automatically added to your project</li>
<li>Start using your new UI components right away</li>
<li>All components are fully customizable</li>
</ul>
</li>
</ol>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">🚀 Getting Started</h2><a id="user-content--getting-started" class="anchor" aria-label="Permalink: 🚀 Getting Started" href="#-getting-started"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">Prerequisites</h3><a id="user-content-prerequisites" class="anchor" aria-label="Permalink: Prerequisites" href="#prerequisites"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<ul dir="auto">
<li>Node.js (Latest LTS version recommended)</li>
<li>One of the supported IDEs:
<ul dir="auto">
<li>Cursor</li>
<li>Windsurf</li>
<li>VSCode (with Cline extension)</li>
</ul>
</li>
</ul>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">Installation</h3><a id="user-content-installation" class="anchor" aria-label="Permalink: Installation" href="#installation"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<ol dir="auto">
<li>
<p dir="auto"><strong>Generate API Key</strong></p>
<ul dir="auto">
<li>Visit <a href="https://21st.dev/magic/console" rel="nofollow">21st.dev Magic Console</a></li>
<li>Generate a new API key</li>
</ul>
</li>
<li>
<p dir="auto"><strong>Choose Installation Method</strong></p>
</li>
</ol>
<div class="markdown-heading" dir="auto"><h4 class="heading-element" dir="auto">Method 1: CLI Installation (Recommended)</h4><a id="user-content-method-1-cli-installation-recommended" class="anchor" aria-label="Permalink: Method 1: CLI Installation (Recommended)" href="#method-1-cli-installation-recommended"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">One command to install and configure MCP for your IDE:</p>
<div class="highlight highlight-source-shell notranslate position-relative overflow-auto" dir="auto" data-snippet-clipboard-copy-content="npx @21st-dev/cli@latest install <client> --api-key <key>"><pre>npx @21st-dev/cli@latest install <span class="pl-k">&lt;</span>client<span class="pl-k">&gt;</span> --api-key <span class="pl-k">&lt;</span>key<span class="pl-k">&gt;</span></pre></div>
<p dir="auto">Supported clients: cursor, windsurf, cline, claude</p>
<div class="markdown-heading" dir="auto"><h4 class="heading-element" dir="auto">Method 2: Manual Configuration</h4><a id="user-content-method-2-manual-configuration" class="anchor" aria-label="Permalink: Method 2: Manual Configuration" href="#method-2-manual-configuration"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">If you prefer manual setup, add this to your IDE's MCP config file:</p>
<div class="highlight highlight-source-json notranslate position-relative overflow-auto" dir="auto" data-snippet-clipboard-copy-content="{
  &quot;mcpServers&quot;: {
    &quot;@21st-dev/magic&quot;: {
      &quot;command&quot;: &quot;npx&quot;,
      &quot;args&quot;: [&quot;-y&quot;, &quot;@21st-dev/magic@latest&quot;, &quot;API_KEY=\&quot;your-api-key\&quot;&quot;]
    }
  }
}"><pre>{
  <span class="pl-ent">"mcpServers"</span>: {
    <span class="pl-ent">"@21st-dev/magic"</span>: {
      <span class="pl-ent">"command"</span>: <span class="pl-s"><span class="pl-pds">"</span>npx<span class="pl-pds">"</span></span>,
      <span class="pl-ent">"args"</span>: [<span class="pl-s"><span class="pl-pds">"</span>-y<span class="pl-pds">"</span></span>, <span class="pl-s"><span class="pl-pds">"</span>@21st-dev/magic@latest<span class="pl-pds">"</span></span>, <span class="pl-s"><span class="pl-pds">"</span>API_KEY=<span class="pl-cce">\"</span>your-api-key<span class="pl-cce">\"</span><span class="pl-pds">"</span></span>]
    }
  }
}</pre></div>
<p dir="auto">Config file locations:</p>
<ul dir="auto">
<li>Cursor: <code>~/.cursor/mcp.json</code></li>
<li>Windsurf: <code>~/.codeium/windsurf/mcp_config.json</code></li>
<li>Cline: <code>~/.cline/mcp_config.json</code></li>
<li>Claude: <code>~/.claude/mcp_config.json</code></li>
</ul>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">❓ FAQ</h2><a id="user-content--faq" class="anchor" aria-label="Permalink: ❓ FAQ" href="#-faq"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">How does Magic AI Agent handle my codebase?</h3><a id="user-content-how-does-magic-ai-agent-handle-my-codebase" class="anchor" aria-label="Permalink: How does Magic AI Agent handle my codebase?" href="#how-does-magic-ai-agent-handle-my-codebase"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">Magic AI Agent only writes or modifies files related to the components it generates. It follows your project's code style and structure, and integrates seamlessly with your existing codebase without affecting other parts of your application.</p>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">Can I customize the generated components?</h3><a id="user-content-can-i-customize-the-generated-components" class="anchor" aria-label="Permalink: Can I customize the generated components?" href="#can-i-customize-the-generated-components"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">Yes! All generated components are fully editable and come with well-structured code. You can modify the styling, functionality, and behavior just like any other React component in your codebase.</p>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">What happens if I run out of generations?</h3><a id="user-content-what-happens-if-i-run-out-of-generations" class="anchor" aria-label="Permalink: What happens if I run out of generations?" href="#what-happens-if-i-run-out-of-generations"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">If you exceed your monthly generation limit, you'll be prompted to upgrade your plan. You can upgrade at any time to continue generating components. Your existing components will remain fully functional.</p>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">How soon do new components get added to 21st.dev's library?</h3><a id="user-content-how-soon-do-new-components-get-added-to-21stdevs-library" class="anchor" aria-label="Permalink: How soon do new components get added to 21st.dev's library?" href="#how-soon-do-new-components-get-added-to-21stdevs-library"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">Authors can publish components to 21st.dev at any time, and Magic Agent will have immediate access to them. This means you'll always have access to the latest components and design patterns from the community.</p>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">Is there a limit to component complexity?</h3><a id="user-content-is-there-a-limit-to-component-complexity" class="anchor" aria-label="Permalink: Is there a limit to component complexity?" href="#is-there-a-limit-to-component-complexity"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">Magic AI Agent can handle components of varying complexity, from simple buttons to complex interactive forms. However, for best results, we recommend breaking down very complex UIs into smaller, manageable components.</p>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">🛠️ Development</h2><a id="user-content-️-development" class="anchor" aria-label="Permalink: 🛠️ Development" href="#️-development"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">Project Structure</h3><a id="user-content-project-structure" class="anchor" aria-label="Permalink: Project Structure" href="#project-structure"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<div class="snippet-clipboard-content notranslate position-relative overflow-auto" data-snippet-clipboard-copy-content="mcp/
├── app/
│   └── components/     # Core UI components
├── types/             # TypeScript type definitions
├── lib/              # Utility functions
└── public/           # Static assets"><pre class="notranslate"><code>mcp/
├── app/
│   └── components/     # Core UI components
├── types/             # TypeScript type definitions
├── lib/              # Utility functions
└── public/           # Static assets
</code></pre></div>
<div class="markdown-heading" dir="auto"><h3 class="heading-element" dir="auto">Key Components</h3><a id="user-content-key-components" class="anchor" aria-label="Permalink: Key Components" href="#key-components"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<ul dir="auto">
<li><code>IdeInstructions</code>: Setup instructions for different IDEs</li>
<li><code>ApiKeySection</code>: API key management interface</li>
<li><code>WelcomeOnboarding</code>: Onboarding flow for new users</li>
</ul>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">🤝 Contributing</h2><a id="user-content--contributing" class="anchor" aria-label="Permalink: 🤝 Contributing" href="#-contributing"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">We welcome contributions! Please join our <a href="https://discord.gg/Qx4rFunHfm" rel="nofollow">Discord community</a> and provide feedback to help improve Magic Agent. The source code is available on <a href="https://github.com/serafimcloud/21st">GitHub</a>.</p>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">👥 Community &amp; Support</h2><a id="user-content--community--support" class="anchor" aria-label="Permalink: 👥 Community &amp; Support" href="#-community--support"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<ul dir="auto">
<li><a href="https://discord.gg/Qx4rFunHfm" rel="nofollow">Discord Community</a> - Join our active community</li>
<li><a href="https://x.com/serafimcloud" rel="nofollow">Twitter</a> - Follow us for updates</li>
</ul>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto"><g-emoji class="g-emoji" alias="warning">⚠️</g-emoji> Beta Notice</h2><a id="user-content-️-beta-notice" class="anchor" aria-label="Permalink: ⚠️ Beta Notice" href="#️-beta-notice"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">Magic Agent is currently in beta. All features are free during this period. We appreciate your feedback and patience as we continue to improve the platform.</p>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">📝 License</h2><a id="user-content--license" class="anchor" aria-label="Permalink: 📝 License" href="#-license"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<p dir="auto">MIT License</p>
<div class="markdown-heading" dir="auto"><h2 class="heading-element" dir="auto">🙏 Acknowledgments</h2><a id="user-content--acknowledgments" class="anchor" aria-label="Permalink: 🙏 Acknowledgments" href="#-acknowledgments"><svg class="octicon octicon-link" viewBox="0 0 16 16" version="1.1" width="16" height="16" aria-hidden="true"><path d="m7.775 3.275 1.25-1.25a3.5 3.5 0 1 1 4.95 4.95l-2.5 2.5a3.5 3.5 0 0 1-4.95 0 .751.751 0 0 1 .018-1.042.751.751 0 0 1 1.042-.018 1.998 1.998 0 0 0 2.83 0l2.5-2.5a2.002 2.002 0 0 0-2.83-2.83l-1.25 1.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042Zm-4.69 9.64a1.998 1.998 0 0 0 2.83 0l1.25-1.25a.751.751 0 0 1 1.042.018.751.751 0 0 1 .018 1.042l-1.25 1.25a3.5 3.5 0 1 1-4.95-4.95l2.5-2.5a3.5 3.5 0 0 1 4.95 0 .751.751 0 0 1-.018 1.042.751.751 0 0 1-1.042.018 1.998 1.998 0 0 0-2.83 0l-2.5 2.5a1.998 1.998 0 0 0 0 2.83Z"></path></svg></a></div>
<ul dir="auto">
<li>Thanks to our beta testers and community members</li>
<li>Special thanks to the Cursor, Windsurf, and Cline teams for their collaboration</li>
<li>Integration with <a href="https://21st.dev" rel="nofollow">21st.dev</a> for component inspiration</li>
<li><a href="https://svgl.app" rel="nofollow">SVGL</a> for logo and brand asset integration</li>
</ul>
<hr>
<p dir="auto">For more information, join our <a href="https://discord.gg/Qx4rFunHfm" rel="nofollow">Discord community</a> or visit <a href="https://21st.dev/magic" rel="nofollow">21st.dev/magic</a>.</p>
</div>`;
const titleOption = [
  {
    label: 'About',
    value: 'About',
  },
  {
    label: 'README',
    value: 'README',
  },
  {
    label: 'FAQ',
    value: 'FAQ',
  },
];
{
  /* <p>dasdsdasdsadasdasdasdadasdadasdasdasdasdasdasdasdasdsada</p> */
}
const MpcDetail: React.FC = () => {
  const [alignment, setAlignment] = React.useState<string | null>('About');
  const { mode } = useContext(ChatContext);
  const { t } = useTranslation();

  const handleAlignment = (event: React.MouseEvent<HTMLElement>, newAlignment: string | null) => {
    setAlignment(newAlignment);
  };

  const goRun = values => {
    console.log(values, 'valuesvaluesvalues');
  };

  return (
    <Spin spinning={false}>
      <div className='page-body p-4 md:p-6 h-[90vh] overflow-auto'>
        <header className='mb-8 pb-6 border-b'>
          <div className='flex items-center gap-3 mb-3'>
            <div className='relative h-8 w-8 overflow-hidden rounded-full'>
              <img
                alt='Firecrawl icon'
                decoding='async'
                data-nimg='fill'
                className='object-contain'
                src='https://avatars.githubusercontent.com/u/135057108?v=4'
                style={{ position: 'absolute', height: '100%', width: '100%', inset: '0px', color: 'transparent' }}
              />
            </div>
            <h1 className='text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight break-words'>Firecrawl</h1>
          </div>

          <div className='flex items-center gap-1.5 mb-3 text-sm'>
            <span className='text-muted-foreground'>Created</span>
            <a
              href='https://github.com/mendableai'
              target='_blank'
              rel='noopener noreferrer'
              className='font-medium hover:underline'
            >
              mendableai
            </a>
          </div>

          <p className='text-base md:text-lg text-muted-foreground max-w-prose'>
            Empowers LLMs with advanced web scraping capabilities for content extraction, crawling, and search
            functionalities.
          </p>
        </header>

        <div className='grid grid-cols-1 md:grid-cols-5 gap-6 md:gap-8'>
          <div className='md:col-span-3'>
            <div dir='ltr' data-orientation='horizontal' className='w-full'>
              <div className='flex items-center justify-between mb-1 flex-wrap'>
                <ToggleButtonGroup
                  value={alignment}
                  exclusive
                  onChange={handleAlignment}
                  aria-label='text alignment'
                  className='p-1 bg-white h-12  '
                >
                  {titleOption?.map(item => {
                    return (
                      <>
                        <ToggleButton className='border-0 rounded-[6px]' value={item?.value}>
                          {item?.label}
                        </ToggleButton>
                      </>
                    );
                  })}
                </ToggleButtonGroup>

                <div className='flex items-center gap-2'>
                  <a
                    href='https://www.npmjs.com/package/firecrawl-mcp'
                    target='_blank'
                    rel='noopener noreferrer'
                    className='inline-flex items-center justify-center whitespace-nowrap text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground rounded-md px-3 gap-2 shrink-0 h-8'
                  >
                    <svg
                      xmlns='http://www.w3.org/2000/svg'
                      width='24'
                      height='24'
                      viewBox='0 0 24 24'
                      fill='none'
                      stroke='currentColor'
                      stroke-width='2'
                      stroke-linecap='round'
                      stroke-linejoin='round'
                      className='h-3.5 w-3.5'
                    >
                      <path d='M16.5 9.4 7.55 4.24'></path>
                      <path d='M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z'></path>
                      <polyline points='3.29 7 12 12 20.71 7'></polyline>
                      <line x1='12' x2='12' y1='22' y2='12'></line>
                    </svg>
                    <span className='text-xs'>NPM Package</span>
                  </a>
                  <a
                    href='https://github.com/mendableai/firecrawl-mcp-server'
                    target='_blank'
                    rel='noopener noreferrer'
                    className='inline-flex items-center justify-center whitespace-nowrap text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground rounded-md px-3 gap-2 shrink-0 h-8'
                  >
                    <svg
                      xmlns='http://www.w3.org/2000/svg'
                      width='24'
                      height='24'
                      viewBox='0 0 24 24'
                      fill='none'
                      stroke='currentColor'
                      stroke-width='2'
                      stroke-linecap='round'
                      stroke-linejoin='round'
                      className='h-3.5 w-3.5'
                    >
                      <path d='M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4'></path>
                      <path d='M9 18c-4.51 2-5-2-7-2'></path>
                    </svg>{' '}
                    <span className='text-xs'>Github Repo</span>
                  </a>
                </div>
              </div>
              {/* body left */}
              <div className='ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 mt-6'>
                <div className='rounded-lg border bg-card text-card-foreground shadow-sm overflow-hidden'>
                  {alignment === 'About' && (
                    <div className='p-5 pt-6 space-y-8'>
                      <div>
                        <h2 className='text-xl md:text-2xl font-semibold mb-3'>About</h2>
                        <p className='text-sm md:text-base leading-relaxed'>
                          Magic empowers developers to create beautiful, modern UI components instantly by using natural
                          language descriptions. It seamlessly integrates with popular IDEs like Cursor, Windsurf, and
                          VSCode (with Cline), providing an AI-powered workflow that streamlines UI development. Access
                          a vast library of pre-built, customizable components inspired by 21st.dev, and see your
                          creations in real-time with full TypeScript and SVGL support. Enhance existing components with
                          advanced features and animations to accelerate your UI development process.
                        </p>
                      </div>
                      <div>
                        <h2 className='text-xl md:text-2xl font-semibold mb-4'>Key Features</h2>
                        <ul className='grid sm:grid-cols-2 gap-3'>
                          <li className='flex items-start gap-3 py-1 list-disc'>
                            <span className='w-1.5 h-1.5 rounded-full  mt-2 shrink-0 bg-black'></span>
                            <span className='text-sm md:text-base'>AI-Powered UI Generation from natural language</span>
                          </li>
                        </ul>
                      </div>
                      <div>
                        <h2 className='text-xl md:text-2xl font-semibold mb-4'>Use Cases</h2>
                        <ul className='grid sm:grid-cols-2 gap-3'>
                          <li className='flex items-start gap-3 py-1'>
                            <span className='w-1.5 h-1.5 rounded-full  mt-2 shrink-0 bg-black'></span>
                            <span className='text-sm md:text-base'>Rapid prototyping of UI components</span>
                          </li>
                        </ul>
                      </div>
                    </div>
                  )}
                  {alignment === 'README' && (
                    <>
                      <MarkdownContext>{aaa.replace(/\\n/gm, '\n')}</MarkdownContext>
                    </>
                  )}
                  {alignment === 'FAQ' && (
                    <>
                      <div className='flex flex-col space-y-1.5 p-6 py-4 px-5 bg-muted/20 border-b'>
                        <h3 className='font-semibold tracking-tight text-xl'>Frequently Asked Questions</h3>
                      </div>
                      <div className='p-5'>
                        <div className='divide-y'>
                          <div className='py-4 first:pt-0 last:pb-0'>
                            <h3 className='text-base sm:text-lg font-medium mb-2'>
                              What is Magic and how does it work?
                            </h3>
                            <p className='text-sm sm:text-base text-muted-foreground'>
                              Magic is an AI-powered tool that generates UI components from natural language
                              descriptions. Simply describe the component you need, and Magic creates it within your IDE
                              (Cursor, Windsurf, VSCode).
                            </p>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
            </div>
          </div>
          <div className='space-y-6 md:col-span-2'>
            <Card
              title={
                <div className='flex'>
                  <div className='flex-1'>{t('parameter_name')}</div>
                  <div className='flex-1'>{t('parameter_value')}</div>
                </div>
              }
            >
              <div className='flex'>
                <div className='w-full'>
                  <Form className='font-[400]' onFinish={goRun} style={{width: '100%'}}>
                    {['app string', 'trace_id string', 'region string']?.map(item => {
                      return (
                        <Form.Item label='' name={item} className='w-full'>
                          <div className='flex w-full'>
                            <div className='font-[400] flex-1'>{item}</div>
                            <Input className='flex-1' placeholder={t('Please_Input')} />
                          </div>
                        </Form.Item>
                      );
                    })}

                    <Form.Item>
                      <Button type='primary' htmlType='submit' className='w-full'>
                        {t('trial_run')}
                      </Button>
                    </Form.Item>
                  </Form>
                </div>
              </div>
            </Card>

            <Card title={<div>{t('run_results')}</div>}>
              <SyntaxHighlighter language='javascript' style={mode === 'dark' ? dark : docco}>
                {`
    function hello() {
      console.log("Hello, world!");
    }
  `}
              </SyntaxHighlighter>
            </Card>
          </div>
        </div>
      </div>
    </Spin>
  );
};

export default MpcDetail;
