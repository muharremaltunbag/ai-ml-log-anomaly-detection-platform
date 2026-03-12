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
            for (var ki = 0; ki < objKeys.length; ki++) {
                var k = objKeys[ki];
                var val = obj[k];
                if (typeof val === 'string') {
                    // Hostname alanları → maskHostname (tam eşleşme)
                    if (HOST_FIELDS.indexOf(k) !== -1) {
                        obj[k] = maskHostname(val);
                    } else {
                        // Diğer string alanları → maskText (metin içi tarama)
                        obj[k] = maskText(val);
                    }
                } else if (typeof val === 'object' && val !== null) {
                    obj[k] = maskJsonDeep(val);
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

    function maskDomNode(node, re) {
        if (!node) return;

        // Text node
        if (node.nodeType === 3) {
            var val = node.nodeValue;
            if (val && re.test(val)) {
                re.lastIndex = 0;
                node.nodeValue = maskText(val);
            }
            return;
        }

        // Element node — script/style'ları atla
        if (node.nodeType === 1) {
            var tag = node.tagName;
            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') return;

            // data-server, title, value attribute'larını maskele
            var attrs = ['data-server', 'title', 'value'];
            for (var ai = 0; ai < attrs.length; ai++) {
                var attrVal = node.getAttribute && node.getAttribute(attrs[ai]);
                if (attrVal && re.test(attrVal)) {
                    re.lastIndex = 0;
                    node.setAttribute(attrs[ai], maskText(attrVal));
                }
            }

            // option.textContent (select dropdown)
            if (tag === 'OPTION' && node.textContent) {
                var optText = node.textContent;
                if (re.test(optText)) {
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
        getMapping: function () {
            var merged = {};
            Object.keys(OVERRIDE_MAP).forEach(function (k) { merged[k] = OVERRIDE_MAP[k]; });
            Object.keys(_dynamicMap).forEach(function (k) { merged[k] = _dynamicMap[k]; });
            return merged;
        },
        addOverride: function (realHost, demoHost) {
            OVERRIDE_MAP[realHost.toLowerCase()] = demoHost;
            _reverseMap[demoHost] = realHost.toLowerCase();
            _cachedRegex = null; // regex yeniden derlenecek
        },
        DEMO_HOST_POOLS: DEMO_HOST_POOLS,
        ALL_DEMO_HOSTS: ALL_DEMO_HOSTS,
        isActive: function () {
            return window.DEMO_MODE === true;
        }
    };

    console.log('[DemoMasking] Demo mode aktif — 3 katmanli koruma.');
    console.log('[DemoMasking] Override mapping:', JSON.stringify(OVERRIDE_MAP));
    console.log('[DemoMasking] Koruma: fetch interceptor + escapeHtml wrapper + MutationObserver');
})();
