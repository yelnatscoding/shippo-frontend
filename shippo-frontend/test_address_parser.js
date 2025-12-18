// Test the address parser directly in Node.js

const testAddress = `Gabriela Hernandez
200 5th Avenue
Spc 48
CA 93203 Arvin
United States`;

// Copy the parseAddress function from app.js
function parseAddress(text) {
    // Handle single-line addresses first (comma or tab separated)
    if (!text.includes('\n') && (text.includes(',') || text.includes('\t'))) {
        return parseInlineAddress(text);
    }

    const lines = text.split('\n').map(line => line.trim()).filter(line => line.length > 0);

    if (lines.length === 0) {
        return null;
    }

    const parsed = {
        name: '',
        street: '',
        city: '',
        state: '',
        zip: ''
    };

    // Common country names to filter out
    const countryNames = ['United States', 'USA', 'US', 'United Kingdom', 'UK', 'Canada', 'Mexico'];

    // Extract state, ZIP, and city from the same line (handles "CA 93203 Arvin" format)
    let stateZipCityFound = false;
    const stateAbbrevs = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'];

    for (let i = 0; i < lines.length; i++) {
        // Check for pattern: "CA 93203 Arvin" or "CA 93203-1234 Arvin"
        const stateZipCityMatch = lines[i].match(/\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\s+(.+)/i);
        if (stateZipCityMatch) {
            const state = stateZipCityMatch[1].toUpperCase();
            if (stateAbbrevs.includes(state)) {
                parsed.state = state;
                parsed.zip = stateZipCityMatch[2];
                parsed.city = stateZipCityMatch[3].trim();
                stateZipCityFound = true;
                lines[i] = ''; // Clear this line
                break;
            }
        }
    }

    // If not found, try traditional extraction
    if (!stateZipCityFound) {
        // Extract ZIP code from anywhere in the text
        let zipFound = false;
        for (let i = 0; i < lines.length; i++) {
            const zipMatch = lines[i].match(/\b(\d{5})(-\d{4})?\b/);
            if (zipMatch) {
                parsed.zip = zipMatch[1];
                zipFound = true;
                lines[i] = lines[i].replace(zipMatch[0], '').trim();
                break;
            }
        }

        // Extract state code
        let stateFound = false;
        for (let i = lines.length - 1; i >= 0; i--) {
            const stateMatch = lines[i].match(/\b([A-Za-z]{2})\b/g);
            if (stateMatch) {
                for (let state of stateMatch) {
                    if (stateAbbrevs.includes(state.toUpperCase())) {
                        parsed.state = state.toUpperCase();
                        stateFound = true;
                        lines[i] = lines[i].replace(new RegExp('\\b' + state + '\\b', 'i'), '').trim();
                        break;
                    }
                }
                if (stateFound) break;
            }
        }

        // Now extract city
        let cityFound = false;

        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i];
            if (!line) continue;

            const cleanLine = line.replace(/[,;]+$/, '').trim();

            // Skip if this is a country name
            if (countryNames.some(country => country.toLowerCase() === cleanLine.toLowerCase())) {
                lines[i] = '';
                continue;
            }

            if (cleanLine && !cityFound && !line.match(/^\d+/)) {
                if (cleanLine.match(/[A-Za-z]{2,}/)) {
                    parsed.city = cleanLine.replace(/,/g, '').trim();
                    cityFound = true;
                    lines[i] = '';
                    break;
                }
            }
        }
    }

    // Filter out empty lines and common country names
    const remainingLines = lines.filter(line => {
        if (!line || line.length === 0) return false;
        const lineLower = line.toLowerCase().trim();
        return !countryNames.some(country => country.toLowerCase() === lineLower);
    });

    // First remaining line is likely the name
    if (remainingLines.length > 0) {
        if (!remainingLines[0].match(/^\d+/) || remainingLines[0].match(/[A-Za-z]/)) {
            parsed.name = remainingLines[0];
            remainingLines.shift();
        }
    }

    // Everything else is the street address
    if (remainingLines.length > 0) {
        parsed.street = remainingLines.join(', ');
    }

    // Validate we got at least some data
    if (!parsed.street && !parsed.city && !parsed.zip) {
        return null;
    }

    return parsed;
}

// Run the test
console.log('Testing address parser...\n');
console.log('Input address:');
console.log(testAddress);
console.log('\n---\n');

const result = parseAddress(testAddress);

console.log('Parsed result:');
console.log(JSON.stringify(result, null, 2));
console.log('\n---\n');

console.log('Field breakdown:');
console.log(`Name:   "${result?.name || '(empty)'}"`);
console.log(`Street: "${result?.street || '(empty)'}"`);
console.log(`City:   "${result?.city || '(empty)'}"`);
console.log(`State:  "${result?.state || '(empty)'}"`);
console.log(`ZIP:    "${result?.zip || '(empty)'}"`);

// Check if correct
const isCorrect =
    result?.name === 'Gabriela Hernandez' &&
    result?.street === '200 5th Avenue, Spc 48' &&
    result?.city === 'Arvin' &&
    result?.state === 'CA' &&
    result?.zip === '93203';

console.log('\n---\n');
console.log(isCorrect ? '✅ PASSED - Address parsed correctly!' : '❌ FAILED - Parsing incorrect');
