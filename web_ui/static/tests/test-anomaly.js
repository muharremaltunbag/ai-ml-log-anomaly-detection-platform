/**
 * Anomaly Module Tests
 */

function runAnomalyTests() {
    const T = TestSuite;
    
    // Test 1: Anomaly fonksiyonları mevcut mu?
    T.assertFunction(window.updateParentAnomalyQuery, 'updateParentAnomalyQuery is a function');
    T.assertFunction(window.displayChatAnomalyResult, 'displayChatAnomalyResult is a function');
    T.assertFunction(window.decodeHtmlEntities, 'decodeHtmlEntities is a function');
    T.assertFunction(window.formatAIResponse, 'formatAIResponse is a function');
    T.assertFunction(window.displayAnomalyAnalysisResult, 'displayAnomalyAnalysisResult is a function');
    T.assertFunction(window.exportAnomalyReport, 'exportAnomalyReport is a function');
    T.assertFunction(window.scheduleFollowUp, 'scheduleFollowUp is a function');
    T.assertFunction(window.saveFollowUp, 'saveFollowUp is a function');
    T.assertFunction(window.formatSection, 'formatSection is a function');
    T.assertFunction(window.highlightNumbers, 'highlightNumbers is a function');
    T.assertFunction(window.parseAIExplanationFromText, 'parseAIExplanationFromText is a function');
    T.assertFunction(window.handleAnalyzeLog, 'handleAnalyzeLog is a function');
    T.assertFunction(window.closeAnomalyModal, 'closeAnomalyModal is a function');
    T.assertFunction(window.displayAnomalyResults, 'displayAnomalyResults is a function');
    
    // Test 2: HTML decode fonksiyonu çalışıyor mu?
    const encodedText = '&lt;div&gt;Test &amp; Example&lt;/div&gt;';
    const decoded = window.decodeHtmlEntities(encodedText);
    T.assert(decoded.includes('<div>'), 'decodeHtmlEntities decodes &lt; correctly');
    T.assert(decoded.includes('&'), 'decodeHtmlEntities decodes &amp; correctly');
    
    // Test 3: Sayı vurgulama çalışıyor mu?
    const textWithNumbers = 'Toplam 1234 log analiz edildi, %95.5 başarı';
    const highlighted = window.highlightNumbers(textWithNumbers);
    T.assert(highlighted.includes('number-highlight'), 'highlightNumbers adds number highlighting');
    T.assert(highlighted.includes('percentage-highlight'), 'highlightNumbers highlights percentages');
    
    // Test 4: AI açıklama parse fonksiyonu
    const sampleText = `Ne Tespit Edildi
    Test anomali bulundu
    Potansiyel Etkiler
    - Etki 1
    - Etki 2`;
    const parsed = window.parseAIExplanationFromText(sampleText);
    T.assertNotNull(parsed, 'parseAIExplanationFromText returns result');
    T.assert(parsed.ne_tespit_edildi !== undefined, 'Parsed result has ne_tespit_edildi');
    T.assert(Array.isArray(parsed.potansiyel_etkiler), 'Parsed result has potansiyel_etkiler array');
}