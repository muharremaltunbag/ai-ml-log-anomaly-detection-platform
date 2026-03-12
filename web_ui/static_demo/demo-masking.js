/**
 * Demo Masking Layer
 * ------------------
 * 3 katmanlı hostname maskeleme:
 *   1) fetch() interceptor  — API response'larında kaynak noktasında maskele
 *   2) escapeHtml wrapper   — render sırasında maskele
 *   3) MutationObserver     — DOM'a eklenen kaçak text node'ları yakala
 *
 * Bu dosya tüm diğer script'lerden ÖNCE yüklenir.
 * window.DEMO_MODE === true ise aktif olur.
 * Mevcut production UI'ya hiçbir etkisi yoktur.
 */

(function () {
    'use strict';

    if (!window.DEMO_MODE) return;

    // ============================================================
    // 1) Demo hostname havuzu
    // ============================================================
    var DEMO_HOST_POOLS = {
        prod:  [],
        stage: [],
        test:  []
    };
    var i;
    for (i = 1; i <= 5; i++) DEMO_HOST_POOLS.prod.push('mongo-prod-node-' + String(i).padStart(2, '0'));
    for (i = 1; i <= 3; i++) DEMO_HOST_POOLS.stage.push('mongo-stage-node-' + String(i).padStart(2, '0'));
    for (i = 1; i <= 3; i++) DEMO_HOST_POOLS.test.push('mongo-test-node-' + String(i).padStart(2, '0'));

    var ALL_DEMO_HOSTS = DEMO_HOST_POOLS.prod.concat(DEMO_HOST_POOLS.stage, DEMO_HOST_POOLS.test);

    // Demo isimlerini hızlı lookup için Set'e al
    var _demoHostSet = {};
    ALL_DEMO_HOSTS.forEach(function (h) { _demoHostSet[h] = true; });

    // ============================================================
    // 2) Sabit override mapping (bilinen hostlar)
    // ============================================================
    var OVERRIDE_MAP = {
        'ecaztrdbmng015': 'mongo-prod-node-01',
        'ecaztrdbmng014': 'mongo-prod-node-02',
        'pplazmongodbn3': 'mongo-prod-node-03'
    };

    // Reverse map: demo -> real (çift maskeleme önleme)
    var _reverseMap = {};
    Object.keys(OVERRIDE_MAP).forEach(function (k) {
        _reverseMap[OVERRIDE_MAP[k]] = k;
    });

    // ============================================================
    // 3) Deterministic hash fonksiyonu
    // ============================================================
    function hashCode(str) {
        var hash = 0;
        for (var j = 0; j < str.length; j++) {
            hash = ((hash << 5) - hash) + str.charCodeAt(j);
            hash |= 0;
        }
        return Math.abs(hash);
    }

    // ============================================================
    // 4) Ana maskeleme fonksiyonları
    // ============================================================
    var _dynamicMap = {};

    function maskHostname(realName) {
        if (!realName || typeof realName !== 'string') return realName;

        var key = realName.trim().toLowerCase();
        if (!key) return realName;

        // Zaten demo ismi mi?
        if (_demoHostSet[key]) return key;

        // Override var mı?
        if (OVERRIDE_MAP[key]) return OVERRIDE_MAP[key];

        // Daha önce eşleştirilmiş mi?
        if (_dynamicMap[key]) return _dynamicMap[key];

        // Hash tabanlı deterministic atama
        var idx = hashCode(key) % ALL_DEMO_HOSTS.length;
        _dynamicMap[key] = ALL_DEMO_HOSTS[idx];
        return _dynamicMap[key];
    }

    // Bilinen tüm gerçek hostname pattern'lerini regex olarak derle
    // Override'lar + dinamik map'teki gerçek isimler
    function _buildReplaceRegex() {
        var keys = Object.keys(OVERRIDE_MAP).concat(Object.keys(_dynamicMap));
        if (keys.length === 0) return null;
        // Uzundan kısaya sırala (greedy match için)
        keys.sort(function (a, b) { return b.length - a.length; });
        // Escape regex special chars
        var escaped = keys.map(function (k) {
            return k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        });
        return new RegExp('(' + escaped.join('|') + ')', 'gi');
    }

    var _cachedRegex = null;
    var _cachedRegexKeyCount = 0;

    function _getRegex() {
        var currentCount = Object.keys(OVERRIDE_MAP).length + Object.keys(_dynamicMap).length;
        if (!_cachedRegex || _cachedRegexKeyCount !== currentCount) {
            _cachedRegex = _buildReplaceRegex();
            _cachedRegexKeyCount = currentCount;
        }
        return _cachedRegex;
    }

    function maskText(text) {
        if (!text || typeof text !== 'string') return text;
        var re = _getRegex();
        if (!re) return text;
        return text.replace(re, function (match) {
            return maskHostname(match);
        });
    }

    // ============================================================
    // 5) KATMAN 1: fetch() interceptor
    //    API response JSON'larındaki hostname alanlarını maskele
    // ============================================================
    var HOST_FIELDS = [
        'host', 'hostname', 'host_name', 'hostName',
        'server', 'server_name', 'serverName', 'source_host',
        'server_id', 'serverId', 'node', 'node_name'
    ];

    // ── Model path maskeleme ──
    var PATH_FIELDS = [
        'model_path', 'modelPath', 'model_file', 'modelFile',
        'file_path', 'filePath', 'config_path', 'configPath'
    ];
    var MASKED_PATH_LABEL = 'server-specific model file';

    function maskModelPath(val) {
        if (!val || typeof val !== 'string') return val;
        // Dosya yolu gibi görünüyorsa maskele
        if (val.indexOf('/') !== -1 || val.indexOf('\\') !== -1) {
            return MASKED_PATH_LABEL;
        }
        return val;
    }

    // ── Client IP maskeleme ──
    var IP_FIELDS = ['client_ip', 'clientIp', 'ip_address', 'ipAddress', 'ip', 'source_ip'];
    var _ipMap = {};
    var _ipCounter = 1;
    // IP regex: x.x.x.x pattern
    var IP_REGEX = /\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b/g;

    function maskIp(ip) {
        if (!ip || typeof ip !== 'string') return ip;
        var key = ip.trim();
        if (_ipMap[key]) return _ipMap[key];
        _ipMap[key] = '10.0.0.' + _ipCounter;
        _ipCounter++;
        return _ipMap[key];
    }

    function maskIpsInText(text) {
        if (!text || typeof text !== 'string') return text;
        return text.replace(IP_REGEX, function (match) {
            return maskIp(match);
        });
    }

    // ── Username maskeleme ──
    var USER_FIELDS = ['username', 'userName', 'user', 'db_user', 'dbUser'];
    var _userMap = {};
    var _userCounter = 1;

    function maskUsername(name) {
        if (!name || typeof name !== 'string') return name;
        var key = name.trim().toLowerCase();
        if (!key || key === 'unknown' || key === 'n/a') return name;
        if (_userMap[key]) return _userMap[key];
        _userMap[key] = 'demo-user-' + String(_userCounter).padStart(2, '0');
        _userCounter++;
        return _userMap[key];
    }

    // ── Marka/şirket metin maskeleme ──
    var BRAND_REPLACEMENTS = [
        [/LCWGPT/g, 'AI Assistant'],
        [/LC Waikiki/gi, 'Demo'],
        [/lcw-test-\d+/gi, 'demo-api-key']
    ];

    // ── Geliştirilmiş maskText: hostname + IP + marka maskeleme ──
    var _origMaskText = maskText;
    maskText = function (text) {
        if (!text || typeof text !== 'string') return text;
        var result = _origMaskText(text);
        result = maskIpsInText(result);
        for (var bi = 0; bi < BRAND_REPLACEMENTS.length; bi++) {
            result = result.replace(BRAND_REPLACEMENTS[bi][0], BRAND_REPLACEMENTS[bi][1]);
        }
        return result;
    };

    // Object key'lerin hostname olup olmadığını test eden heuristik:
    // Bilinen override'lar + dynamic map + hostname pattern (alfanumerik, 6+ char)
    var HOSTNAME_KEY_PATTERN = /^[a-zA-Z][a-zA-Z0-9._-]{5,}$/;

    function _isLikelyHostnameKey(key) {
        if (OVERRIDE_MAP[key.toLowerCase()]) return true;
        if (_dynamicMap[key.toLowerCase()]) return true;
        // hostStates gibi object'lerde key'ler genellikle hostname'dir
        // güvenli heuristik: alfanumerik, 6+ karakter, sayı içermeli
        if (HOSTNAME_KEY_PATTERN.test(key) && /\d/.test(key)) return true;
        return false;
    }

    function maskJsonDeep(obj) {
        if (obj === null || obj === undefined) return obj;
        if (typeof obj === 'string') return maskText(obj);
        if (Array.isArray(obj)) {
            for (var idx = 0; idx < obj.length; idx++) {
                obj[idx] = maskJsonDeep(obj[idx]);
            }
            return obj;
        }
        if (typeof obj === 'object') {
            var objKeys = Object.keys(obj);
            var renamedKeys = []; // key rename'leri topla, sonra uygula

            for (var ki = 0; ki < objKeys.length; ki++) {
                var k = objKeys[ki];
                var val = obj[k];

                // ── Value maskeleme ──
                if (typeof val === 'string') {
                    if (PATH_FIELDS.indexOf(k) !== -1) {
                        obj[k] = maskModelPath(val);
                    } else if (IP_FIELDS.indexOf(k) !== -1) {
                        obj[k] = maskIp(val);
                    } else if (USER_FIELDS.indexOf(k) !== -1) {
                        obj[k] = maskUsername(val);
                    } else if (HOST_FIELDS.indexOf(k) !== -1) {
                        obj[k] = maskHostname(val);
                    } else {
                        obj[k] = maskText(val);
                    }
                } else if (typeof val === 'object' && val !== null) {
                    obj[k] = maskJsonDeep(val);
                }

                // ── Key maskeleme (hostname olarak kullanılan key'ler) ──
                if (_isLikelyHostnameKey(k)) {
                    var maskedKey = maskHostname(k);
                    if (maskedKey !== k) {
                        renamedKeys.push({ oldKey: k, newKey: maskedKey });
                    }
                }
            }

            // Key rename'leri uygula
            for (var ri = 0; ri < renamedKeys.length; ri++) {
                var rk = renamedKeys[ri];
                if (!obj.hasOwnProperty(rk.newKey)) {
                    obj[rk.newKey] = obj[rk.oldKey];
                    delete obj[rk.oldKey];
                }
            }

            return obj;
        }
        return obj;
    }

    // Orijinal fetch'i sakla ve intercept et
    var _originalFetch = window.fetch;

    window.fetch = function demoFetch(input, init) {
        return _originalFetch.call(this, input, init).then(function (response) {
            // Sadece API endpoint'lerini yakala
            var url = (typeof input === 'string') ? input : (input && input.url ? input.url : '');
            if (url.indexOf('/api/') === -1) return response;

            // Response'u clone et, JSON'u parse edip maskele
            var cloned = response.clone();
            var originalHeaders = response.headers;
            var originalStatus = response.status;
            var originalStatusText = response.statusText;

            return cloned.text().then(function (bodyText) {
                var maskedBody = bodyText;
                try {
                    var json = JSON.parse(bodyText);
                    maskJsonDeep(json);
                    maskedBody = JSON.stringify(json);
                } catch (e) {
                    // JSON değilse plain text olarak maskele
                    maskedBody = maskText(bodyText);
                }

                return new Response(maskedBody, {
                    status: originalStatus,
                    statusText: originalStatusText,
                    headers: originalHeaders
                });
            });
        });
    };

    // ============================================================
    // 6) KATMAN 2: escapeHtml wrapper
    //    script-ui.js'de tanımlanan escapeHtml'i sarmalayarak
    //    render sırasında maskeleme yap
    // ============================================================

    // escapeHtml henüz tanımlanmadı (script-ui.js daha sonra yüklenecek)
    // Bu yüzden DOMContentLoaded'da wrap ediyoruz
    function wrapEscapeHtml() {
        if (typeof window.escapeHtml === 'function' && !window.escapeHtml._demoWrapped) {
            var _origEscapeHtml = window.escapeHtml;
            window.escapeHtml = function demoEscapeHtml(text) {
                var escaped = _origEscapeHtml(text);
                return maskText(escaped);
            };
            window.escapeHtml._demoWrapped = true;
        }
    }

    // script-ui.js yüklendikten sonra wrap et
    // Birden fazla deneme: hem DOMContentLoaded hem de polling
    document.addEventListener('DOMContentLoaded', wrapEscapeHtml);

    // Ayrıca her 100ms'de kontrol et (script yükleme sırası garantisi için)
    var _wrapAttempts = 0;
    var _wrapInterval = setInterval(function () {
        _wrapAttempts++;
        if (window.escapeHtml || _wrapAttempts > 50) {
            wrapEscapeHtml();
            clearInterval(_wrapInterval);
        }
    }, 100);

    // ============================================================
    // 7) KATMAN 3: MutationObserver
    //    DOM'a eklenen text node'larda kaçak hostname varsa yakala
    // ============================================================
    function initMutationObserver() {
        if (typeof MutationObserver === 'undefined') return;

        var observer = new MutationObserver(function (mutations) {
            var re = _getRegex();
            if (!re) return;

            for (var mi = 0; mi < mutations.length; mi++) {
                var mutation = mutations[mi];

                // Yeni eklenen node'ları tara
                if (mutation.addedNodes) {
                    for (var ni = 0; ni < mutation.addedNodes.length; ni++) {
                        var node = mutation.addedNodes[ni];
                        maskDomNode(node, re);
                    }
                }

                // Text/attribute değişikliklerini yakala
                if (mutation.type === 'characterData' && mutation.target) {
                    var textVal = mutation.target.nodeValue;
                    if (textVal && re.test(textVal)) {
                        re.lastIndex = 0;
                        mutation.target.nodeValue = maskText(textVal);
                    }
                }
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true
        });
    }

    // Dosya yolu pattern'i: /xxx/yyy veya C:\xxx\yyy
    var PATH_LIKE_REGEX = /(?:\/[\w.-]+){2,}|(?:[A-Z]:\\[\w.-]+){2,}/;

    function maskDomNode(node, re) {
        if (!node) return;

        // Text node
        if (node.nodeType === 3) {
            var val = node.nodeValue;
            if (!val) return;
            var changed = false;
            if (re && re.test(val)) {
                re.lastIndex = 0;
                val = maskText(val);
                changed = true;
            }
            if (IP_REGEX.test(val)) {
                IP_REGEX.lastIndex = 0;
                val = maskIpsInText(val);
                changed = true;
            }
            // Marka metinleri
            for (var bri = 0; bri < BRAND_REPLACEMENTS.length; bri++) {
                if (BRAND_REPLACEMENTS[bri][0].test(val)) {
                    BRAND_REPLACEMENTS[bri][0].lastIndex = 0;
                    val = val.replace(BRAND_REPLACEMENTS[bri][0], BRAND_REPLACEMENTS[bri][1]);
                    changed = true;
                }
            }
            if (changed) node.nodeValue = val;
            return;
        }

        // Element node — script/style'ları atla
        if (node.nodeType === 1) {
            var tag = node.tagName;
            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') return;

            // ── .model-path class'lı elementler → path maskeleme ──
            if (node.classList && node.classList.contains('model-path')) {
                // title attribute'taki tam path'i maskele
                if (node.getAttribute('title')) {
                    node.setAttribute('title', MASKED_PATH_LABEL);
                }
                // Görünür text'i de maskele
                if (node.textContent && PATH_LIKE_REGEX.test(node.textContent)) {
                    node.textContent = MASKED_PATH_LABEL;
                }
            }

            // ── data-server, title, value attribute'larını maskele ──
            var attrs = ['data-server', 'title', 'value'];
            for (var ai = 0; ai < attrs.length; ai++) {
                var attrVal = node.getAttribute && node.getAttribute(attrs[ai]);
                if (!attrVal) continue;

                var attrChanged = false;
                // Dosya yolu içeren title → maskele
                if (attrs[ai] === 'title' && PATH_LIKE_REGEX.test(attrVal)) {
                    attrVal = MASKED_PATH_LABEL;
                    attrChanged = true;
                }
                if (re && re.test(attrVal)) {
                    re.lastIndex = 0;
                    attrVal = maskText(attrVal);
                    attrChanged = true;
                }
                if (IP_REGEX.test(attrVal)) {
                    IP_REGEX.lastIndex = 0;
                    attrVal = maskIpsInText(attrVal);
                    attrChanged = true;
                }
                if (attrChanged) node.setAttribute(attrs[ai], attrVal);
            }

            // ── #mlModelFilePath elementi → path maskeleme ──
            if (node.id === 'mlModelFilePath' && node.textContent) {
                if (PATH_LIKE_REGEX.test(node.textContent) || node.textContent.indexOf('.pkl') !== -1 || node.textContent.indexOf('.joblib') !== -1) {
                    node.textContent = MASKED_PATH_LABEL;
                }
            }

            // option.textContent (select dropdown)
            if (tag === 'OPTION' && node.textContent) {
                var optText = node.textContent;
                if (re && re.test(optText)) {
                    re.lastIndex = 0;
                    node.textContent = maskText(optText);
                    if (node.value && re.test(node.value)) {
                        re.lastIndex = 0;
                        node.value = maskText(node.value);
                    }
                }
            }

            // Alt node'ları recursive tara
            var children = node.childNodes;
            for (var ci = 0; ci < children.length; ci++) {
                maskDomNode(children[ci], re);
            }
        }
    }

    // Body hazır olduğunda observer'ı başlat
    if (document.body) {
        initMutationObserver();
    } else {
        document.addEventListener('DOMContentLoaded', initMutationObserver);
    }

    // ============================================================
    // 8) Public API → window.DemoMasking
    // ============================================================
    window.DemoMasking = {
        maskHostname: maskHostname,
        maskText: maskText,
        maskJsonDeep: maskJsonDeep,
        maskModelPath: maskModelPath,
        maskIp: maskIp,
        maskUsername: maskUsername,
        getMapping: function () {
            var merged = {};
            Object.keys(OVERRIDE_MAP).forEach(function (k) { merged[k] = OVERRIDE_MAP[k]; });
            Object.keys(_dynamicMap).forEach(function (k) { merged[k] = _dynamicMap[k]; });
            return merged;
        },
        getIpMapping: function () { return Object.assign({}, _ipMap); },
        getUserMapping: function () { return Object.assign({}, _userMap); },
        addOverride: function (realHost, demoHost) {
            OVERRIDE_MAP[realHost.toLowerCase()] = demoHost;
            _reverseMap[demoHost] = realHost.toLowerCase();
            _cachedRegex = null;
        },
        DEMO_HOST_POOLS: DEMO_HOST_POOLS,
        ALL_DEMO_HOSTS: ALL_DEMO_HOSTS,
        MASKED_PATH_LABEL: MASKED_PATH_LABEL,
        isActive: function () {
            return window.DEMO_MODE === true;
        }
    };

    console.log('[DemoMasking] Demo mode aktif — 3 katmanli koruma.');
    console.log('[DemoMasking] Maskeleme: hostname + model_path + client_ip + username');
    console.log('[DemoMasking] Koruma: fetch interceptor + escapeHtml wrapper + MutationObserver');
})();
