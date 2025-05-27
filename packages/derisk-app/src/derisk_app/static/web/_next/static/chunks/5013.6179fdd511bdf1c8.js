"use strict";(self.webpackChunk_N_E=self.webpackChunk_N_E||[]).push([[5013],{5013:function(e,t,i){i.r(t),i.d(t,{default:function(){return a}});var s=i(49686),n=[{key:"obwhite",config:{base:"vs",inherit:!0,rules:[{foreground:"09885A",token:"comment"}],colors:{"editor.foreground":"#3B3B3B","editor.background":"#FFFFFF","editor.selectionBackground":"#BAD6FD","editor.lineHighlightBackground":"#00000012","editorCursor.foreground":"#000000","editorWhitespace.foreground":"#BFBFBF"}}},{key:"obdark",config:{base:"vs-dark",inherit:!0,rules:[{foreground:"F7F9FB",token:"identifier"},{foreground:"98D782",token:"number"}],colors:{}}}],a=class{constructor(){this.modelOptionsMap=new Map}setup(e=["mysql","obmysql","oboracle"]){e.forEach(e=>{switch(e){case"mysql":i.e(7994).then(i.bind(i,77994)).then(e=>{e.setup(this)});break;case"obmysql":i.e(1424).then(i.bind(i,91424)).then(e=>{e.setup(this)});break;case"oboracle":i.e(1144).then(i.bind(i,41144)).then(e=>{e.setup(this)})}}),n.forEach(e=>{s.j6.defineTheme(e.key,e.config)})}setModelOptions(e,t){this.modelOptionsMap.set(e,t)}}},49686:function(e,t,i){i.d(t,{j6:function(){return u.editor},Mj:function(){return u.languages}}),i(49149),i(64696),i(54881),i(13972),i(24676),i(89963),i(87822),i(11899),i(71256),i(41484),i(65378),i(6231),i(66676),i(58),i(41888),i(12414),i(89640),i(3400),i(46292),i(49399),i(38557),i(8387),i(86620),i(11314),i(29256),i(33201),i(96840),i(98324),i(47506),i(89961),i(93059),i(83322),i(96792),i(41305),i(9515),i(42100),i(1185),i(33727),i(37478),i(82583),i(80582),i(24243),i(69759),i(59857),i(99928),i(45461),i(1880),i(83266),i(28764),i(81989),i(53355),i(68363);var s,n,a,o,r,l,d,c,h,p,g,u=i(26187),m=Object.defineProperty,b=Object.getOwnPropertyDescriptor,x=Object.getOwnPropertyNames,f=Object.prototype.hasOwnProperty,y={};m(y,"__esModule",{value:!0}),((e,t,i)=>{if(t&&"object"==typeof t||"function"==typeof t)for(let s of x(t))f.call(e,s)||"default"===s||m(e,s,{get:()=>t[s],enumerable:!(i=b(t,s))||i.enumerable})})(y,u),(s=d||(d={}))[s.None=0]="None",s[s.CommonJS=1]="CommonJS",s[s.AMD=2]="AMD",s[s.UMD=3]="UMD",s[s.System=4]="System",s[s.ES2015=5]="ES2015",s[s.ESNext=99]="ESNext",(n=c||(c={}))[n.None=0]="None",n[n.Preserve=1]="Preserve",n[n.React=2]="React",n[n.ReactNative=3]="ReactNative",n[n.ReactJSX=4]="ReactJSX",n[n.ReactJSXDev=5]="ReactJSXDev",(a=h||(h={}))[a.CarriageReturnLineFeed=0]="CarriageReturnLineFeed",a[a.LineFeed=1]="LineFeed",(o=p||(p={}))[o.ES3=0]="ES3",o[o.ES5=1]="ES5",o[o.ES2015=2]="ES2015",o[o.ES2016=3]="ES2016",o[o.ES2017=4]="ES2017",o[o.ES2018=5]="ES2018",o[o.ES2019=6]="ES2019",o[o.ES2020=7]="ES2020",o[o.ESNext=99]="ESNext",o[o.JSON=100]="JSON",o[o.Latest=99]="Latest",(r=g||(g={}))[r.Classic=1]="Classic",r[r.NodeJs=2]="NodeJs";var v=class{constructor(e,t,i,s){this._onDidChange=new y.Emitter,this._onDidExtraLibsChange=new y.Emitter,this._extraLibs=Object.create(null),this._removedExtraLibs=Object.create(null),this._eagerModelSync=!1,this.setCompilerOptions(e),this.setDiagnosticsOptions(t),this.setWorkerOptions(i),this.setInlayHintsOptions(s),this._onDidExtraLibsChangeTimeout=-1}get onDidChange(){return this._onDidChange.event}get onDidExtraLibsChange(){return this._onDidExtraLibsChange.event}get workerOptions(){return this._workerOptions}get inlayHintsOptions(){return this._inlayHintsOptions}getExtraLibs(){return this._extraLibs}addExtraLib(e,t){let i;if(i=void 0===t?`ts:extralib-${Math.random().toString(36).substring(2,15)}`:t,this._extraLibs[i]&&this._extraLibs[i].content===e)return{dispose:()=>{}};let s=1;return this._removedExtraLibs[i]&&(s=this._removedExtraLibs[i]+1),this._extraLibs[i]&&(s=this._extraLibs[i].version+1),this._extraLibs[i]={content:e,version:s},this._fireOnDidExtraLibsChangeSoon(),{dispose:()=>{let e=this._extraLibs[i];e&&e.version===s&&(delete this._extraLibs[i],this._removedExtraLibs[i]=s,this._fireOnDidExtraLibsChangeSoon())}}}setExtraLibs(e){for(let e in this._extraLibs)this._removedExtraLibs[e]=this._extraLibs[e].version;if(this._extraLibs=Object.create(null),e&&e.length>0)for(let t of e){let e=t.filePath||`ts:extralib-${Math.random().toString(36).substring(2,15)}`,i=t.content,s=1;this._removedExtraLibs[e]&&(s=this._removedExtraLibs[e]+1),this._extraLibs[e]={content:i,version:s}}this._fireOnDidExtraLibsChangeSoon()}_fireOnDidExtraLibsChangeSoon(){-1===this._onDidExtraLibsChangeTimeout&&(this._onDidExtraLibsChangeTimeout=window.setTimeout(()=>{this._onDidExtraLibsChangeTimeout=-1,this._onDidExtraLibsChange.fire(void 0)},0))}getCompilerOptions(){return this._compilerOptions}setCompilerOptions(e){this._compilerOptions=e||Object.create(null),this._onDidChange.fire(void 0)}getDiagnosticsOptions(){return this._diagnosticsOptions}setDiagnosticsOptions(e){this._diagnosticsOptions=e||Object.create(null),this._onDidChange.fire(void 0)}setWorkerOptions(e){this._workerOptions=e||Object.create(null),this._onDidChange.fire(void 0)}setInlayHintsOptions(e){this._inlayHintsOptions=e||Object.create(null),this._onDidChange.fire(void 0)}setMaximumWorkerIdleTime(e){}setEagerModelSync(e){this._eagerModelSync=e}getEagerModelSync(){return this._eagerModelSync}},w=new v({allowNonTsExtensions:!0,target:99},{noSemanticValidation:!1,noSyntaxValidation:!1,onlyVisible:!1},{},{}),S=new v({allowNonTsExtensions:!0,allowJs:!0,target:99},{noSemanticValidation:!0,noSyntaxValidation:!1,onlyVisible:!1},{},{});function H(){return i.e(3526).then(i.bind(i,63526))}y.languages.typescript={ModuleKind:d,JsxEmit:c,NewLineKind:h,ScriptTarget:p,ModuleResolutionKind:g,typescriptVersion:"4.4.4",typescriptDefaults:w,javascriptDefaults:S,getTypeScriptWorker:()=>H().then(e=>e.getTypeScriptWorker()),getJavaScriptWorker:()=>H().then(e=>e.getJavaScriptWorker())},y.languages.onLanguage("typescript",()=>H().then(e=>e.setupTypeScript(w))),y.languages.onLanguage("javascript",()=>H().then(e=>e.setupJavaScript(S)));/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/var _=Object.defineProperty,O=Object.getOwnPropertyDescriptor,j=Object.getOwnPropertyNames,C=Object.prototype.hasOwnProperty,L={};_(L,"__esModule",{value:!0}),((e,t,i)=>{if(t&&"object"==typeof t||"function"==typeof t)for(let s of j(t))C.call(e,s)||"default"===s||_(e,s,{get:()=>t[s],enumerable:!(i=O(t,s))||i.enumerable})})(L,u);var k=class{constructor(e,t,i){this._onDidChange=new L.Emitter,this._languageId=e,this.setOptions(t),this.setModeConfiguration(i)}get onDidChange(){return this._onDidChange.event}get languageId(){return this._languageId}get modeConfiguration(){return this._modeConfiguration}get diagnosticsOptions(){return this.options}get options(){return this._options}setOptions(e){this._options=e||Object.create(null),this._onDidChange.fire(this)}setDiagnosticsOptions(e){this.setOptions(e)}setModeConfiguration(e){this._modeConfiguration=e||Object.create(null),this._onDidChange.fire(this)}},D={validate:!0,lint:{compatibleVendorPrefixes:"ignore",vendorPrefix:"warning",duplicateProperties:"warning",emptyRules:"warning",importStatement:"ignore",boxModel:"ignore",universalSelector:"ignore",zeroUnits:"ignore",fontFaceProperties:"warning",hexColorLength:"error",argumentsInColorFunction:"error",unknownProperties:"warning",ieHack:"ignore",unknownVendorSpecificProperties:"ignore",propertyIgnoredDueToDisplay:"warning",important:"ignore",float:"ignore",idSelector:"ignore"},data:{useDefaultDataProvider:!0}},E={completionItems:!0,hovers:!0,documentSymbols:!0,definitions:!0,references:!0,documentHighlights:!0,rename:!0,colors:!0,foldingRanges:!0,diagnostics:!0,selectionRanges:!0},M=new k("css",D,E),P=new k("scss",D,E),R=new k("less",D,E);function q(){return i.e(335).then(i.bind(i,50335))}L.languages.css={cssDefaults:M,lessDefaults:R,scssDefaults:P},L.languages.onLanguage("less",()=>{q().then(e=>e.setupMode(R))}),L.languages.onLanguage("scss",()=>{q().then(e=>e.setupMode(P))}),L.languages.onLanguage("css",()=>{q().then(e=>e.setupMode(M))});/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/var F=Object.defineProperty,T=Object.getOwnPropertyDescriptor,N=Object.getOwnPropertyNames,I=Object.prototype.hasOwnProperty,J={};F(J,"__esModule",{value:!0}),((e,t,i)=>{if(t&&"object"==typeof t||"function"==typeof t)for(let s of N(t))I.call(e,s)||"default"===s||F(e,s,{get:()=>t[s],enumerable:!(i=T(t,s))||i.enumerable})})(J,u);var z=new class{constructor(e,t,i){this._onDidChange=new J.Emitter,this._languageId=e,this.setDiagnosticsOptions(t),this.setModeConfiguration(i)}get onDidChange(){return this._onDidChange.event}get languageId(){return this._languageId}get modeConfiguration(){return this._modeConfiguration}get diagnosticsOptions(){return this._diagnosticsOptions}setDiagnosticsOptions(e){this._diagnosticsOptions=e||Object.create(null),this._onDidChange.fire(this)}setModeConfiguration(e){this._modeConfiguration=e||Object.create(null),this._onDidChange.fire(this)}}("json",{validate:!0,allowComments:!0,schemas:[],enableSchemaRequest:!1,schemaRequest:"warning",schemaValidation:"warning",comments:"error",trailingCommas:"error"},{documentFormattingEdits:!0,documentRangeFormattingEdits:!0,completionItems:!0,hovers:!0,documentSymbols:!0,tokens:!0,colors:!0,foldingRanges:!0,diagnostics:!0,selectionRanges:!0});J.languages.json={jsonDefaults:z},J.languages.register({id:"json",extensions:[".json",".bowerrc",".jshintrc",".jscsrc",".eslintrc",".babelrc",".har"],aliases:["JSON","json"],mimetypes:["application/json"]}),J.languages.onLanguage("json",()=>{i.e(6818).then(i.bind(i,70005)).then(e=>e.setupMode(z))});/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/var B=Object.defineProperty,A=Object.getOwnPropertyDescriptor,V=Object.getOwnPropertyNames,W=Object.prototype.hasOwnProperty,Q={};B(Q,"__esModule",{value:!0}),((e,t,i)=>{if(t&&"object"==typeof t||"function"==typeof t)for(let s of V(t))W.call(e,s)||"default"===s||B(e,s,{get:()=>t[s],enumerable:!(i=A(t,s))||i.enumerable})})(Q,u);var U=class{constructor(e,t,i){this._onDidChange=new Q.Emitter,this._languageId=e,this.setOptions(t),this.setModeConfiguration(i)}get onDidChange(){return this._onDidChange.event}get languageId(){return this._languageId}get options(){return this._options}get modeConfiguration(){return this._modeConfiguration}setOptions(e){this._options=e||Object.create(null),this._onDidChange.fire(this)}setModeConfiguration(e){this._modeConfiguration=e||Object.create(null),this._onDidChange.fire(this)}},X={format:{tabSize:4,insertSpaces:!1,wrapLineLength:120,unformatted:'default": "a, abbr, acronym, b, bdo, big, br, button, cite, code, dfn, em, i, img, input, kbd, label, map, object, q, samp, select, small, span, strong, sub, sup, textarea, tt, var',contentUnformatted:"pre",indentInnerHtml:!1,preserveNewLines:!0,maxPreserveNewLines:void 0,indentHandlebars:!1,endWithNewline:!1,extraLiners:"head, body, /html",wrapAttributes:"auto"},suggest:{},data:{useDefaultDataProvider:!0}};function G(e){return{completionItems:!0,hovers:!0,documentSymbols:!0,links:!0,documentHighlights:!0,rename:!0,colors:!0,foldingRanges:!0,selectionRanges:!0,diagnostics:e===$,documentFormattingEdits:e===$,documentRangeFormattingEdits:e===$}}var $="html",Y="handlebars",K="razor",Z=ea($,X,G($)),ee=Z.defaults,et=ea(Y,X,G(Y)),ei=et.defaults,es=ea(K,X,G(K)),en=es.defaults;function ea(e,t=X,s=G(e)){let n;let a=new U(e,t,s),o=Q.languages.onLanguage(e,async()=>{n=(await i.e(1002).then(i.bind(i,81002))).setupMode(a)});return{defaults:a,dispose(){o.dispose(),n?.dispose(),n=void 0}}}Q.languages.html={htmlDefaults:ee,razorDefaults:en,handlebarDefaults:ei,htmlLanguageService:Z,handlebarLanguageService:et,razorLanguageService:es,registerHTMLLanguageService:ea};var eo=i(87309);/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"abap",extensions:[".abap"],aliases:["abap","ABAP"],loader:()=>i.e(4485).then(i.bind(i,64485))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"apex",extensions:[".cls"],aliases:["Apex","apex"],mimetypes:["text/x-apex-source","text/x-apex"],loader:()=>i.e(5167).then(i.bind(i,35167))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"azcli",extensions:[".azcli"],aliases:["Azure CLI","azcli"],loader:()=>i.e(337).then(i.bind(i,80337))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"bat",extensions:[".bat",".cmd"],aliases:["Batch","bat"],loader:()=>i.e(5853).then(i.bind(i,95853))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"bicep",extensions:[".bicep"],aliases:["Bicep"],loader:()=>i.e(2137).then(i.bind(i,12137))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"cameligo",extensions:[".mligo"],aliases:["Cameligo"],loader:()=>i.e(9932).then(i.bind(i,99932))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"clojure",extensions:[".clj",".cljs",".cljc",".edn"],aliases:["clojure","Clojure"],loader:()=>i.e(2417).then(i.bind(i,22417))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"coffeescript",extensions:[".coffee"],aliases:["CoffeeScript","coffeescript","coffee"],mimetypes:["text/x-coffeescript","text/coffeescript"],loader:()=>i.e(8640).then(i.bind(i,48640))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"c",extensions:[".c",".h"],aliases:["C","c"],loader:()=>i.e(8013).then(i.bind(i,98013))}),(0,eo.H)({id:"cpp",extensions:[".cpp",".cc",".cxx",".hpp",".hh",".hxx"],aliases:["C++","Cpp","cpp"],loader:()=>i.e(8013).then(i.bind(i,98013))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"csharp",extensions:[".cs",".csx",".cake"],aliases:["C#","csharp"],loader:()=>i.e(7085).then(i.bind(i,87085))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"csp",extensions:[],aliases:["CSP","csp"],loader:()=>i.e(1261).then(i.bind(i,51261))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"css",extensions:[".css"],aliases:["CSS","css"],mimetypes:["text/css"],loader:()=>i.e(155).then(i.bind(i,60155))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"dart",extensions:[".dart"],aliases:["Dart","dart"],mimetypes:["text/x-dart-source","text/x-dart"],loader:()=>i.e(1682).then(i.bind(i,91682))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"dockerfile",extensions:[".dockerfile"],filenames:["Dockerfile"],aliases:["Dockerfile"],loader:()=>i.e(779).then(i.bind(i,90779))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"ecl",extensions:[".ecl"],aliases:["ECL","Ecl","ecl"],loader:()=>i.e(1503).then(i.bind(i,91503))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"elixir",extensions:[".ex",".exs"],aliases:["Elixir","elixir","ex"],loader:()=>i.e(6974).then(i.bind(i,6974))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"flow9",extensions:[".flow"],aliases:["Flow9","Flow","flow9","flow"],loader:()=>i.e(3844).then(i.bind(i,93844))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"fsharp",extensions:[".fs",".fsi",".ml",".mli",".fsx",".fsscript"],aliases:["F#","FSharp","fsharp"],loader:()=>i.e(3881).then(i.bind(i,33881))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"go",extensions:[".go"],aliases:["Go"],loader:()=>i.e(6369).then(i.bind(i,86369))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"graphql",extensions:[".graphql",".gql"],aliases:["GraphQL","graphql","gql"],mimetypes:["application/graphql"],loader:()=>i.e(8863).then(i.bind(i,78863))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"handlebars",extensions:[".handlebars",".hbs"],aliases:["Handlebars","handlebars","hbs"],mimetypes:["text/x-handlebars-template"],loader:()=>i.e(7324).then(i.bind(i,7324))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"hcl",extensions:[".tf",".tfvars",".hcl"],aliases:["Terraform","tf","HCL","hcl"],loader:()=>i.e(1012).then(i.bind(i,61012))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"html",extensions:[".html",".htm",".shtml",".xhtml",".mdoc",".jsp",".asp",".aspx",".jshtm"],aliases:["HTML","htm","html","xhtml"],mimetypes:["text/html","text/x-jshtm","text/template","text/ng-template"],loader:()=>i.e(5606).then(i.bind(i,15606))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"ini",extensions:[".ini",".properties",".gitconfig"],filenames:["config",".gitattributes",".gitconfig",".editorconfig"],aliases:["Ini","ini"],loader:()=>i.e(9163).then(i.bind(i,49163))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"java",extensions:[".java",".jav"],aliases:["Java","java"],mimetypes:["text/x-java-source","text/x-java"],loader:()=>i.e(545).then(i.bind(i,50545))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"javascript",extensions:[".js",".es6",".jsx",".mjs"],firstLine:"^#!.*\\bnode",filenames:["jakefile"],aliases:["JavaScript","javascript","js"],mimetypes:["text/javascript"],loader:()=>i.e(4613).then(i.bind(i,34613))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"julia",extensions:[".jl"],aliases:["julia","Julia"],loader:()=>i.e(6287).then(i.bind(i,26287))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"kotlin",extensions:[".kt"],aliases:["Kotlin","kotlin"],mimetypes:["text/x-kotlin-source","text/x-kotlin"],loader:()=>i.e(1491).then(i.bind(i,11491))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"less",extensions:[".less"],aliases:["Less","less"],mimetypes:["text/x-less","text/less"],loader:()=>i.e(9028).then(i.bind(i,29028))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"lexon",extensions:[".lex"],aliases:["Lexon"],loader:()=>i.e(646).then(i.bind(i,50646))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"lua",extensions:[".lua"],aliases:["Lua","lua"],loader:()=>i.e(5702).then(i.bind(i,5702))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"liquid",extensions:[".liquid",".html.liquid"],aliases:["Liquid","liquid"],mimetypes:["application/liquid"],loader:()=>i.e(1143).then(i.bind(i,81143))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"m3",extensions:[".m3",".i3",".mg",".ig"],aliases:["Modula-3","Modula3","modula3","m3"],loader:()=>i.e(3927).then(i.bind(i,3927))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"markdown",extensions:[".md",".markdown",".mdown",".mkdn",".mkd",".mdwn",".mdtxt",".mdtext"],aliases:["Markdown","markdown"],loader:()=>i.e(4494).then(i.bind(i,84494))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"mips",extensions:[".s"],aliases:["MIPS","MIPS-V"],mimetypes:["text/x-mips","text/mips","text/plaintext"],loader:()=>i.e(1590).then(i.bind(i,51590))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"msdax",extensions:[".dax",".msdax"],aliases:["DAX","MSDAX"],loader:()=>i.e(9495).then(i.bind(i,59495))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"mysql",extensions:[],aliases:["MySQL","mysql"],loader:()=>i.e(3427).then(i.bind(i,63427))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"objective-c",extensions:[".m"],aliases:["Objective-C"],loader:()=>i.e(1038).then(i.bind(i,31038))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"pascal",extensions:[".pas",".p",".pp"],aliases:["Pascal","pas"],mimetypes:["text/x-pascal-source","text/x-pascal"],loader:()=>i.e(7315).then(i.bind(i,37315))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"pascaligo",extensions:[".ligo"],aliases:["Pascaligo","ligo"],loader:()=>i.e(927).then(i.bind(i,50927))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"perl",extensions:[".pl"],aliases:["Perl","pl"],loader:()=>i.e(8427).then(i.bind(i,38427))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"pgsql",extensions:[],aliases:["PostgreSQL","postgres","pg","postgre"],loader:()=>i.e(7886).then(i.bind(i,37886))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"php",extensions:[".php",".php4",".php5",".phtml",".ctp"],aliases:["PHP","php"],mimetypes:["application/x-php"],loader:()=>i.e(9711).then(i.bind(i,99711))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"pla",extensions:[".pla"],loader:()=>i.e(2606).then(i.bind(i,72606))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"postiats",extensions:[".dats",".sats",".hats"],aliases:["ATS","ATS/Postiats"],loader:()=>i.e(4484).then(i.bind(i,4484))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"powerquery",extensions:[".pq",".pqm"],aliases:["PQ","M","Power Query","Power Query M"],loader:()=>i.e(3012).then(i.bind(i,73012))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"powershell",extensions:[".ps1",".psm1",".psd1"],aliases:["PowerShell","powershell","ps","ps1"],loader:()=>i.e(6765).then(i.bind(i,96765))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"proto",extensions:[".proto"],aliases:["protobuf","Protocol Buffers"],loader:()=>i.e(8504).then(i.bind(i,68504))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"pug",extensions:[".jade",".pug"],aliases:["Pug","Jade","jade"],loader:()=>i.e(5558).then(i.bind(i,5558))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"python",extensions:[".py",".rpy",".pyw",".cpy",".gyp",".gypi"],aliases:["Python","py"],firstLine:"^#!/.*\\bpython[0-9.-]*\\b",loader:()=>i.e(4136).then(i.bind(i,84136))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"qsharp",extensions:[".qs"],aliases:["Q#","qsharp"],loader:()=>i.e(6379).then(i.bind(i,6379))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"r",extensions:[".r",".rhistory",".rmd",".rprofile",".rt"],aliases:["R","r"],loader:()=>i.e(1291).then(i.bind(i,41291))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"razor",extensions:[".cshtml"],aliases:["Razor","razor"],mimetypes:["text/x-cshtml"],loader:()=>i.e(8079).then(i.bind(i,98079))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"redis",extensions:[".redis"],aliases:["redis"],loader:()=>i.e(1093).then(i.bind(i,91093))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"redshift",extensions:[],aliases:["Redshift","redshift"],loader:()=>i.e(5226).then(i.bind(i,20724))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"restructuredtext",extensions:[".rst"],aliases:["reStructuredText","restructuredtext"],loader:()=>i.e(8396).then(i.bind(i,8396))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"ruby",extensions:[".rb",".rbx",".rjs",".gemspec",".pp"],filenames:["rakefile","Gemfile"],aliases:["Ruby","rb"],loader:()=>i.e(4120).then(i.bind(i,54120))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"rust",extensions:[".rs",".rlib"],aliases:["Rust","rust"],loader:()=>i.e(5).then(i.bind(i,40005))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"sb",extensions:[".sb"],aliases:["Small Basic","sb"],loader:()=>i.e(7860).then(i.bind(i,27860))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"scala",extensions:[".scala",".sc",".sbt"],aliases:["Scala","scala","SBT","Sbt","sbt","Dotty","dotty"],mimetypes:["text/x-scala-source","text/x-scala","text/x-sbt","text/x-dotty"],loader:()=>i.e(3854).then(i.bind(i,63854))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"scheme",extensions:[".scm",".ss",".sch",".rkt"],aliases:["scheme","Scheme"],loader:()=>i.e(4970).then(i.bind(i,34970))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"scss",extensions:[".scss"],aliases:["Sass","sass","scss"],mimetypes:["text/x-scss","text/scss"],loader:()=>i.e(7875).then(i.bind(i,87875))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"shell",extensions:[".sh",".bash"],aliases:["Shell","sh"],loader:()=>i.e(243).then(i.bind(i,20243))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"sol",extensions:[".sol"],aliases:["sol","solidity","Solidity"],loader:()=>i.e(164).then(i.bind(i,20164))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"aes",extensions:[".aes"],aliases:["aes","sophia","Sophia"],loader:()=>i.e(7595).then(i.bind(i,67595))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"sparql",extensions:[".rq"],aliases:["sparql","SPARQL"],loader:()=>i.e(6016).then(i.bind(i,96016))}),i(84556),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"st",extensions:[".st",".iecst",".iecplc",".lc3lib"],aliases:["StructuredText","scl","stl"],loader:()=>i.e(4067).then(i.bind(i,44067))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"swift",aliases:["Swift","swift"],extensions:[".swift"],mimetypes:["text/swift"],loader:()=>i.e(9146).then(i.bind(i,79146))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"systemverilog",extensions:[".sv",".svh"],aliases:["SV","sv","SystemVerilog","systemverilog"],loader:()=>i.e(6692).then(i.bind(i,36692))}),(0,eo.H)({id:"verilog",extensions:[".v",".vh"],aliases:["V","v","Verilog","verilog"],loader:()=>i.e(6692).then(i.bind(i,36692))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"tcl",extensions:[".tcl"],aliases:["tcl","Tcl","tcltk","TclTk","tcl/tk","Tcl/Tk"],loader:()=>i.e(7676).then(i.bind(i,7676))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"twig",extensions:[".twig"],aliases:["Twig","twig"],mimetypes:["text/x-twig"],loader:()=>i.e(739).then(i.bind(i,80739))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"typescript",extensions:[".ts",".tsx"],aliases:["TypeScript","ts","typescript"],mimetypes:["text/typescript"],loader:()=>i.e(7134).then(i.bind(i,77134))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"vb",extensions:[".vb"],aliases:["Visual Basic","vb"],loader:()=>i.e(7707).then(i.bind(i,47707))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"xml",extensions:[".xml",".dtd",".ascx",".csproj",".config",".wxi",".wxl",".wxs",".xaml",".svg",".svgz",".opf",".xsl"],firstLine:"(\\<\\?xml.*)|(\\<svg)|(\\<\\!doctype\\s+svg)",aliases:["XML","xml"],mimetypes:["text/xml","application/xml","application/xaml+xml","application/xml-dtd"],loader:()=>i.e(7280).then(i.bind(i,83361))}),/*!-----------------------------------------------------------------------------
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Version: 0.31.0(252e010eb73ddc2fa1a37c1dade7bf35d87106cd)
 * Released under the MIT license
 * https://github.com/microsoft/monaco-editor/blob/main/LICENSE.txt
 *-----------------------------------------------------------------------------*/(0,eo.H)({id:"yaml",extensions:[".yaml",".yml"],aliases:["YAML","yaml","YML","yml"],mimetypes:["application/x-yaml","text/x-yaml"],loader:()=>i.e(4022).then(i.bind(i,34022))}),i(66443),i(95741),i(66266);var er=i(826),el=i(13441),ed=i(36913);class ec extends el.R6{constructor(){super({id:"editor.action.forceRetokenize",label:ed.N("forceRetokenize","Developer: Force Retokenize"),alias:"Developer: Force Retokenize",precondition:void 0})}run(e,t){if(!t.hasModel())return;let i=t.getModel();i.resetTokenization();let s=new er.G(!0);i.forceTokenization(i.getLineCount()),s.stop(),console.log(`tokenization took ${s.elapsed()}`)}}(0,el.Qr)(ec),i(23663),i(8082),self.MonacoEnvironment=(l={editorWorkerService:"static/editor.worker.js"},{globalAPI:!1,getWorkerUrl:function(e,t){var s=i.p,n=(s?s.replace(/\/$/,"")+"/":"")+l[t];if(/^((http:)|(https:)|(file:)|(\/\/))/.test(n)){var a=String(window.location),o=a.substr(0,a.length-window.location.hash.length-window.location.search.length-window.location.pathname.length);if(n.substring(0,o.length)!==o){/^(\/\/)/.test(n)&&(n=window.location.protocol+n);var r="/*"+t+'*/importScripts("'+n+'");',d=new Blob([r],{type:"application/javascript"});return URL.createObjectURL(d)}}return n}})}}]);