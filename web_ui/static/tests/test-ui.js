/**
 * UI Module Tests
 */

function runUITests() {
    const T = TestSuite;
    
    // Test 1: UI fonksiyonları mevcut mu?
    T.assertFunction(window.updateStatus, 'updateStatus is a function');
    T.assertFunction(window.showNotification, 'showNotification is a function');
    T.assertFunction(window.showLoader, 'showLoader is a function');
    T.assertFunction(window.showModal, 'showModal is a function');
    T.assertFunction(window.closeModal, 'closeModal is a function');
    T.assertFunction(window.escapeHtml, 'escapeHtml is a function');
    T.assertFunction(window.formatJSON, 'formatJSON is a function');
    
    // Test 2: escapeHtml XSS koruması çalışıyor mu?
    const dangerousHtml = '<script>alert("XSS")</script>';
    const escaped = window.escapeHtml(dangerousHtml);
    T.assert(!escaped.includes('<script>'), 'escapeHtml removes script tags');
    T.assert(escaped.includes('&lt;script&gt;'), 'escapeHtml properly escapes HTML');
    
    // Test 3: formatJSON çalışıyor mu?
    const testObj = { name: 'test', value: 123 };
    const formatted = window.formatJSON(testObj);
    T.assert(formatted.includes('json-key'), 'formatJSON adds CSS classes for keys');
    T.assert(formatted.includes('json-number'), 'formatJSON adds CSS classes for numbers');
    
    // Test 4: Special character escaping
    const specialChars = '"Hello & <World>"';
    const escapedSpecial = window.escapeHtml(specialChars);
    T.assert(escapedSpecial.includes('&amp;'), 'escapeHtml escapes ampersand');
    T.assert(escapedSpecial.includes('&quot;'), 'escapeHtml escapes quotes');
    T.assert(escapedSpecial.includes('&lt;'), 'escapeHtml escapes less-than');
    T.assert(escapedSpecial.includes('&gt;'), 'escapeHtml escapes greater-than');
}