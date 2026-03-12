/**
 * Demo Masking Layer
 * ------------------
 * Dinamik hostname maskeleme + hassas veri gizleme.
 * Bu dosya tüm diğer script'lerden ÖNCE yüklenir.
 *
 * Kullanım: window.DEMO_MODE === true ise aktif olur.
 * Mevcut production UI'ya hiçbir etkisi yoktur.
 */

(function () {
    'use strict';

    if (!window.DEMO_MODE) return;

    // ============================================================
    // 1) Demo hostname havuzu
    // ============================================================
    const DEMO_HOST_POOLS = {
        prod:  Array.from({ length: 5 }, (_, i) => `mongo-prod-node-${String(i + 1).padStart(2, '0')}`),
        stage: Array.from({ length: 3 }, (_, i) => `mongo-stage-node-${String(i + 1).padStart(2, '0')}`),
        test:  Array.from({ length: 3 }, (_, i) => `mongo-test-node-${String(i + 1).padStart(2, '0')}`)
    };

    // Tüm havuz isimleri düz liste (round-robin fallback)
    const ALL_DEMO_HOSTS = [
        ...DEMO_HOST_POOLS.prod,
        ...DEMO_HOST_POOLS.stage,
        ...DEMO_HOST_POOLS.test
    ];

    // ============================================================
    // 2) Sabit override mapping (bilinen hostlar)
    // ============================================================
    const OVERRIDE_MAP = {
        'ecaztrdbmng015': 'mongo-prod-node-01',
        'ecaztrdbmng014': 'mongo-prod-node-02',
        'pplazmongodbn3': 'mongo-prod-node-03'
    };

    // ============================================================
    // 3) Deterministic hash → index (bilinmeyen hostlar için)
    // ============================================================
    function hashCode(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            hash = ((hash << 5) - hash) + str.charCodeAt(i);
            hash |= 0; // 32-bit int
        }
        return Math.abs(hash);
    }

    // ============================================================
    // 4) Ana maskeleme fonksiyonu
    // ============================================================
    const _dynamicMap = {};  // runtime'da oluşan mapping cache

    /**
     * maskHostname('ecaztrdbmng015') → 'mongo-prod-node-01'
     * maskHostname('unknownHost123') → deterministic demo ismi
     */
    function maskHostname(realName) {
        if (!realName || typeof realName !== 'string') return realName;

        const key = realName.trim().toLowerCase();

        // Zaten demo ismi mi? (tekrar maskelemeyi önle)
        if (ALL_DEMO_HOSTS.includes(key)) return key;

        // Override var mı?
        if (OVERRIDE_MAP[key]) return OVERRIDE_MAP[key];

        // Daha önce eşleştirilmiş mi?
        if (_dynamicMap[key]) return _dynamicMap[key];

        // Hash tabanlı deterministic atama
        const idx = hashCode(key) % ALL_DEMO_HOSTS.length;
        _dynamicMap[key] = ALL_DEMO_HOSTS[idx];
        return _dynamicMap[key];
    }

    /**
     * Bir metin bloğundaki tüm olası hostname'leri maskeler.
     * Basit regex: alfanumerik, tire, alt çizgi, nokta — 6+ karakter
     * (PATCH 2'de daha ince ayar yapılacak)
     */
    function maskText(text) {
        if (!text || typeof text !== 'string') return text;
        // Şimdilik sadece bilinen override'ları replace et
        let result = text;
        for (const [real, demo] of Object.entries(OVERRIDE_MAP)) {
            // case insensitive global replace
            result = result.replace(new RegExp(real, 'gi'), demo);
        }
        return result;
    }

    // ============================================================
    // 5) Public API → window.DemoMasking
    // ============================================================
    window.DemoMasking = {
        maskHostname: maskHostname,
        maskText: maskText,
        getMapping: function () {
            return { ...OVERRIDE_MAP, ..._dynamicMap };
        },
        DEMO_HOST_POOLS: DEMO_HOST_POOLS,
        ALL_DEMO_HOSTS: ALL_DEMO_HOSTS,
        isActive: function () {
            return window.DEMO_MODE === true;
        }
    };

    console.log('[DemoMasking] Demo mode aktif. Override count:', Object.keys(OVERRIDE_MAP).length);
})();
