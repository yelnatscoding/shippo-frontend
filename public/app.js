// Shipping Label Tool - Frontend Application
const ShippingApp = {
    config: {
        apiUrl: window.location.hostname === 'localhost' ? 'http://localhost:3000/api' : '/api',
        providers: ['shippo', 'easypost', 'shipengine', 'easyship']
    },

    state: {
        currentTab: 'rates',
        selectedRate: null,
        ratesData: null,
        fromAddress: null,
        toAddress: null,
        parcel: null,
        history: []
    },

    // Package presets
    packagePresets: {
        small: { length: 6, width: 4, height: 2, weight: 0.5 },
        medium: { length: 10, width: 8, height: 6, weight: 2 },
        large: { length: 16, width: 12, height: 8, weight: 5 },
        custom: { length: null, width: null, height: null, weight: null }
    },

    // Initialize app
    init() {
        console.log('Initializing Shipping App...');
        this.bindEvents();
        this.restoreFormData();
        this.loadHistory();
    },

    // Bind event listeners
    bindEvents() {
        // Compare rates button
        document.getElementById('compare-rates-btn').addEventListener('click', () => {
            this.compareRates();
        });

        // Validate address button
        document.getElementById('validate-btn').addEventListener('click', () => {
            this.validateAddress();
        });

        // Refresh history button
        document.getElementById('refresh-history-btn').addEventListener('click', () => {
            this.loadHistory();
        });

        // Address parsing buttons
        document.getElementById('parse-to-address').addEventListener('click', () => {
            this.parseAndFillAddress('to');
        });

        document.getElementById('parse-val-address').addEventListener('click', () => {
            this.parseAndFillAddress('val');
        });

        // Package preset radio buttons
        document.querySelectorAll('input[name="preset"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                this.applyPackagePreset(e.target.value);
            });
        });

        // Auto-save form data on input
        const formInputs = [
            'to-name', 'to-street', 'to-city', 'to-state', 'to-zip',
            'length', 'width', 'height', 'weight'
        ];

        formInputs.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => this.saveFormData());
            }
        });
    },

    // Parse and fill address from pasted text
    parseAndFillAddress(prefix) {
        const pasteText = document.getElementById(`${prefix}-paste`).value.trim();

        if (!pasteText) {
            this.showError('Please paste an address first');
            return;
        }

        const parsed = this.parseAddress(pasteText);

        if (parsed) {
            document.getElementById(`${prefix}-name`).value = parsed.name || '';
            document.getElementById(`${prefix}-street`).value = parsed.street || '';
            document.getElementById(`${prefix}-city`).value = parsed.city || '';
            document.getElementById(`${prefix}-state`).value = parsed.state || '';
            document.getElementById(`${prefix}-zip`).value = parsed.zip || '';

            // Clear the paste textarea
            document.getElementById(`${prefix}-paste`).value = '';

            this.showSuccess('Address parsed successfully!');
            this.saveFormData();
        } else {
            this.showError('Could not parse address. Please check the format.');
        }
    },

    // Parse address from text block
    parseAddress(text) {
        // Handle single-line addresses first (comma or tab separated)
        if (!text.includes('\n') && (text.includes(',') || text.includes('\t'))) {
            return this.parseInlineAddress(text);
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

        // Extract ZIP code from anywhere in the text
        let zipFound = false;
        for (let i = 0; i < lines.length; i++) {
            const zipMatch = lines[i].match(/\b(\d{5})(-\d{4})?\b/);
            if (zipMatch) {
                parsed.zip = zipMatch[1];
                zipFound = true;
                // Remove zip from the line for easier processing
                lines[i] = lines[i].replace(zipMatch[0], '').trim();
                break;
            }
        }

        // Extract state code (2 uppercase letters, possibly lowercase)
        let stateFound = false;
        const stateAbbrevs = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'];

        for (let i = lines.length - 1; i >= 0; i--) {
            const stateMatch = lines[i].match(/\b([A-Za-z]{2})\b/g);
            if (stateMatch) {
                for (let state of stateMatch) {
                    if (stateAbbrevs.includes(state.toUpperCase())) {
                        parsed.state = state.toUpperCase();
                        stateFound = true;
                        // Remove state from the line
                        lines[i] = lines[i].replace(new RegExp('\\b' + state + '\\b', 'i'), '').trim();
                        break;
                    }
                }
                if (stateFound) break;
            }
        }

        // Now extract city - look for city, state pattern or standalone city
        let cityFound = false;
        for (let i = lines.length - 1; i >= 0; i--) {
            const line = lines[i];
            if (!line) continue;

            // Remove any trailing commas or special chars
            const cleanLine = line.replace(/[,;]+$/, '').trim();

            // If this line still has text and we haven't found city yet
            if (cleanLine && !cityFound && !line.match(/^\d+/)) {
                // Check if this looks like a city (has letters, not just numbers)
                if (cleanLine.match(/[A-Za-z]{2,}/)) {
                    parsed.city = cleanLine.replace(/,/g, '').trim();
                    cityFound = true;
                    lines[i] = ''; // Clear this line
                    break;
                }
            }
        }

        // Filter out empty lines again
        const remainingLines = lines.filter(line => line.length > 0);

        // First remaining line is likely the name
        if (remainingLines.length > 0) {
            // Check if first line looks like a name (not all numbers)
            if (!remainingLines[0].match(/^\d+/) || remainingLines[0].match(/[A-Za-z]/)) {
                parsed.name = remainingLines[0];
                remainingLines.shift();
            }
        }

        // Everything else is the street address
        if (remainingLines.length > 0) {
            parsed.street = remainingLines.join(', ');
        }

        // If we couldn't parse in lines, try the whole text as one block
        if (!parsed.street && !parsed.city && !parsed.state && !parsed.zip) {
            return this.parseInlineAddress(text);
        }

        // Validate we got at least some data
        if (!parsed.street && !parsed.city && !parsed.zip) {
            return null;
        }

        return parsed;
    },

    // Parse single-line or comma-separated addresses
    parseInlineAddress(text) {
        const parsed = {
            name: '',
            street: '',
            city: '',
            state: '',
            zip: ''
        };

        // Split by comma or tab
        const parts = text.split(/[,\t]+/).map(p => p.trim()).filter(p => p);

        if (parts.length === 0) return null;

        // Extract ZIP from any part
        for (let i = 0; i < parts.length; i++) {
            const zipMatch = parts[i].match(/\b(\d{5})(-\d{4})?\b/);
            if (zipMatch) {
                parsed.zip = zipMatch[1];
                parts[i] = parts[i].replace(zipMatch[0], '').trim();
            }
        }

        // Extract state
        const stateAbbrevs = ['AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL','IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT','NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI','SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY','DC'];

        for (let i = parts.length - 1; i >= 0; i--) {
            const stateMatch = parts[i].match(/\b([A-Za-z]{2})\b/);
            if (stateMatch && stateAbbrevs.includes(stateMatch[1].toUpperCase())) {
                parsed.state = stateMatch[1].toUpperCase();
                parts[i] = parts[i].replace(stateMatch[0], '').trim();
                break;
            }
        }

        // Filter empty parts
        const cleanParts = parts.filter(p => p.length > 0);

        // Heuristic: name, street, city pattern
        if (cleanParts.length >= 3) {
            parsed.name = cleanParts[0];
            parsed.street = cleanParts[1];
            parsed.city = cleanParts[2];
        } else if (cleanParts.length === 2) {
            // Could be name + street, or street + city
            if (cleanParts[0].match(/^\d+/)) {
                // Starts with number, likely street address
                parsed.street = cleanParts[0];
                parsed.city = cleanParts[1];
            } else {
                parsed.name = cleanParts[0];
                parsed.street = cleanParts[1];
            }
        } else if (cleanParts.length === 1) {
            // Just one part, assume it's street
            parsed.street = cleanParts[0];
        }

        return parsed;
    },

    // Apply package preset
    applyPackagePreset(preset) {
        const dims = this.packagePresets[preset];

        if (preset === 'custom') {
            // Don't change values for custom
            return;
        }

        document.getElementById('length').value = dims.length || '';
        document.getElementById('width').value = dims.width || '';
        document.getElementById('height').value = dims.height || '';
        document.getElementById('weight').value = dims.weight || '';
    },

    // Save form data to localStorage
    saveFormData() {
        const formData = {
            toAddress: {
                name: document.getElementById('to-name').value,
                street1: document.getElementById('to-street').value,
                city: document.getElementById('to-city').value,
                state: document.getElementById('to-state').value,
                zip: document.getElementById('to-zip').value
            },
            parcel: {
                length: document.getElementById('length').value,
                width: document.getElementById('width').value,
                height: document.getElementById('height').value,
                weight: document.getElementById('weight').value
            }
        };

        localStorage.setItem('shipmentDraft', JSON.stringify(formData));
    },

    // Restore form data from localStorage
    restoreFormData() {
        const saved = localStorage.getItem('shipmentDraft');
        if (!saved) return;

        try {
            const formData = JSON.parse(saved);

            if (formData.toAddress) {
                document.getElementById('to-name').value = formData.toAddress.name || '';
                document.getElementById('to-street').value = formData.toAddress.street1 || '';
                document.getElementById('to-city').value = formData.toAddress.city || '';
                document.getElementById('to-state').value = formData.toAddress.state || '';
                document.getElementById('to-zip').value = formData.toAddress.zip || '';
            }

            if (formData.parcel) {
                document.getElementById('length').value = formData.parcel.length || '';
                document.getElementById('width').value = formData.parcel.width || '';
                document.getElementById('height').value = formData.parcel.height || '';
                document.getElementById('weight').value = formData.parcel.weight || '';
            }
        } catch (e) {
            console.error('Error restoring form data:', e);
        }
    },

    // Compare rates
    async compareRates() {
        try {
            // Validate inputs
            const toAddress = {
                name: document.getElementById('to-name').value.trim(),
                street1: document.getElementById('to-street').value.trim(),
                city: document.getElementById('to-city').value.trim(),
                state: document.getElementById('to-state').value.trim().toUpperCase(),
                zip: document.getElementById('to-zip').value.trim(),
                country: 'US'
            };

            const fromAddress = {
                name: 'JunQ Trading Technology Inc.',
                street1: '2755 E Philadelphia St',
                city: 'Ontario',
                state: 'CA',
                zip: '91761',
                country: 'US'
            };

            const parcel = {
                length: parseFloat(document.getElementById('length').value),
                width: parseFloat(document.getElementById('width').value),
                height: parseFloat(document.getElementById('height').value),
                weight: parseFloat(document.getElementById('weight').value)
            };

            // Validate required fields
            if (!toAddress.name || !toAddress.street1 || !toAddress.city || !toAddress.state || !toAddress.zip) {
                this.showError('Please fill in all address fields');
                return;
            }

            if (!parcel.length || !parcel.width || !parcel.height || !parcel.weight) {
                this.showError('Please fill in all package dimensions');
                return;
            }

            // Store for later use
            this.state.fromAddress = fromAddress;
            this.state.toAddress = toAddress;
            this.state.parcel = parcel;

            // Show loading
            this.showLoading('Comparing rates from all providers...');

            // Call API
            const response = await axios.post(`${this.config.apiUrl}/rates`, {
                from_address: fromAddress,
                to_address: toAddress,
                parcel: parcel
            });

            this.hideLoading();

            if (response.data.success) {
                this.state.ratesData = response.data.data;
                this.renderRates(response.data.data, response.data.errors);
            } else {
                this.showError(response.data.error || 'Failed to get rates');
            }

        } catch (error) {
            this.hideLoading();
            console.error('Error comparing rates:', error);
            this.showError(error.response?.data?.error || error.message || 'Failed to compare rates');
        }
    },

    // Render rates results
    renderRates(ratesData, errors) {
        const container = document.getElementById('rates-results');

        let html = '';

        // Check if we have any rates
        const totalRates = Object.values(ratesData).reduce((sum, rates) => sum + (rates?.length || 0), 0);

        if (totalRates === 0) {
            html = `
                <div class="alert alert-warning">
                    <i class="bi bi-exclamation-triangle"></i>
                    <strong>No rates found</strong>
                    <p class="mb-0">No shipping rates were available from any provider. Please check your shipping details.</p>
                </div>
            `;

            // Show errors
            if (errors && Object.keys(errors).length > 0) {
                html += '<div class="alert alert-danger mt-3"><strong>Errors:</strong><ul class="mb-0">';
                Object.entries(errors).forEach(([provider, error]) => {
                    html += `<li><strong>${provider}:</strong> ${error}</li>`;
                });
                html += '</ul></div>';
            }

            container.innerHTML = html;
            return;
        }

        // Group rates by provider
        Object.entries(ratesData).forEach(([provider, rates]) => {
            if (!rates || rates.length === 0) return;

            html += `
                <div class="provider-section">
                    <div class="provider-header d-flex justify-content-between align-items-center">
                        <div>
                            <span class="provider-name">${provider}</span>
                            <span class="provider-count ms-2">(${rates.length} options)</span>
                        </div>
                        <span class="badge bg-primary">${rates.length}</span>
                    </div>
                    <div class="provider-rates">
            `;

            // Sort rates by price
            rates.sort((a, b) => parseFloat(a.amount) - parseFloat(b.amount));

            rates.forEach(rate => {
                const deliveryInfo = rate.estimated_days
                    ? `${rate.estimated_days} day${rate.estimated_days > 1 ? 's' : ''}`
                    : 'Delivery time varies';

                html += `
                    <div class="rate-card" onclick="ShippingApp.selectRate('${rate.object_id}', '${provider}')">
                        <div class="d-flex justify-content-between align-items-start">
                            <div>
                                <div class="rate-carrier">${rate.carrier || provider.toUpperCase()}</div>
                                <div class="rate-service">${rate.servicelevel_name}</div>
                                <div class="rate-delivery">
                                    <i class="bi bi-clock"></i> ${deliveryInfo}
                                </div>
                            </div>
                            <div class="text-end">
                                <div class="rate-price">$${parseFloat(rate.amount).toFixed(2)}</div>
                                <button class="btn btn-sm btn-primary mt-2" onclick="event.stopPropagation(); ShippingApp.purchaseLabel('${rate.object_id}', '${provider}')">
                                    Purchase
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            });

            html += `
                    </div>
                </div>
            `;
        });

        // Show errors if any
        if (errors && Object.keys(errors).length > 0) {
            html += '<div class="alert alert-warning mt-3"><strong>Some providers had errors:</strong><ul class="mb-0">';
            Object.entries(errors).forEach(([provider, error]) => {
                html += `<li><strong>${provider}:</strong> ${error}</li>`;
            });
            html += '</ul></div>';
        }

        container.innerHTML = html;
    },

    // Select a rate
    selectRate(rateId, provider) {
        this.state.selectedRate = { rateId, provider };

        // Visual feedback
        document.querySelectorAll('.rate-card').forEach(card => {
            card.classList.remove('selected');
        });

        event.currentTarget.classList.add('selected');
    },

    // Purchase label
    async purchaseLabel(rateId, provider) {
        try {
            const confirmed = confirm('Purchase this shipping label?');
            if (!confirmed) return;

            this.showLoading('Purchasing label and uploading to Google Drive...');

            const response = await axios.post(`${this.config.apiUrl}/purchase`, {
                rate_id: rateId,
                provider: provider,
                format: 'PDF',
                from_address: this.state.fromAddress,
                to_address: this.state.toAddress
            });

            this.hideLoading();

            if (response.data.success) {
                const labelData = response.data.data;

                // Save to history
                await this.saveToHistory(labelData);

                // Show success message
                this.showPurchaseSuccess(labelData, response.data.warning);

                // Refresh history
                this.loadHistory();

            } else {
                this.showError(response.data.error || 'Failed to purchase label');
            }

        } catch (error) {
            this.hideLoading();
            console.error('Error purchasing label:', error);
            this.showError(error.response?.data?.error || error.message || 'Failed to purchase label');
        }
    },

    // Show purchase success
    showPurchaseSuccess(labelData, warning) {
        const container = document.getElementById('rates-results');

        let html = `
            <div class="purchase-success">
                <h5><i class="bi bi-check-circle"></i> Label Purchased Successfully!</h5>
                <div class="row">
                    <div class="col-md-6">
                        <p><strong>Tracking Number:</strong><br>
                        <span class="tracking-number">${labelData.tracking_number}</span></p>
                        <p><strong>Carrier:</strong> ${labelData.carrier} - ${labelData.service}</p>
                        <p><strong>Cost:</strong> $${parseFloat(labelData.cost).toFixed(2)}</p>
                    </div>
                    <div class="col-md-6">
                        <p><strong>From:</strong> ${labelData.from_address.city}, ${labelData.from_address.state}</p>
                        <p><strong>To:</strong> ${labelData.to_address.name}<br>
                        ${labelData.to_address.city}, ${labelData.to_address.state} ${labelData.to_address.zip}</p>
                    </div>
                </div>
        `;

        if (warning) {
            html += `<div class="warning-message mt-3"><i class="bi bi-exclamation-triangle"></i> ${warning}</div>`;
        }

        html += `<div class="mt-3">`;

        if (labelData.google_drive_link) {
            html += `
                <a href="${labelData.google_drive_link}" target="_blank" class="btn btn-primary me-2">
                    <i class="bi bi-cloud-download"></i> Open in Google Drive
                </a>
            `;
        }

        if (labelData.label_url_temp) {
            html += `
                <a href="${labelData.label_url_temp}" target="_blank" class="btn btn-outline-primary me-2">
                    <i class="bi bi-download"></i> Download PDF
                </a>
            `;
        }

        html += `
                <button class="btn btn-success" onclick="ShippingApp.compareRates()">
                    <i class="bi bi-plus-circle"></i> Create Another Label
                </button>
            </div>
        </div>
        `;

        container.innerHTML = html;
    },

    // Validate address
    async validateAddress() {
        try {
            const address = {
                name: document.getElementById('val-name').value.trim(),
                street1: document.getElementById('val-street').value.trim(),
                city: document.getElementById('val-city').value.trim(),
                state: document.getElementById('val-state').value.trim().toUpperCase(),
                zip: document.getElementById('val-zip').value.trim(),
                country: 'US'
            };

            if (!address.street1 || !address.city || !address.state || !address.zip) {
                this.showError('Please fill in all address fields');
                return;
            }

            this.showLoading('Validating address...');

            const response = await axios.post(`${this.config.apiUrl}/validate`, {
                address: address,
                provider: 'auto'
            });

            this.hideLoading();

            if (response.data.success) {
                this.renderValidationResult(response.data.data);
            } else {
                this.showError(response.data.error || 'Failed to validate address');
            }

        } catch (error) {
            this.hideLoading();
            console.error('Error validating address:', error);
            this.showError(error.response?.data?.error || error.message || 'Failed to validate address');
        }
    },

    // Render validation result
    renderValidationResult(result) {
        const container = document.getElementById('validation-results');

        const alertClass = result.is_valid ? 'alert-success validation-success' : 'alert-warning validation-warning';
        const icon = result.is_valid ? 'check-circle-fill' : 'exclamation-triangle-fill';

        let html = `
            <div class="alert ${alertClass}">
                <h6><i class="bi bi-${icon}"></i> ${result.is_valid ? 'Address is valid' : 'Address needs correction'}</h6>
        `;

        if (result.messages && result.messages.length > 0) {
            html += '<ul class="mb-0">';
            result.messages.forEach(msg => {
                html += `<li>${msg}</li>`;
            });
            html += '</ul>';
        }

        html += '</div>';

        // Show comparison if address was corrected
        if (result.suggested && result.suggested.street1 !== result.original.street1) {
            html += `
                <div class="address-compare">
                    <div class="address-box">
                        <div class="address-label">Original Address</div>
                        <div>${result.original.street1}</div>
                        <div>${result.original.city}, ${result.original.state} ${result.original.zip}</div>
                    </div>
                    <div class="address-box">
                        <div class="address-label">Suggested Address</div>
                        <div>${result.suggested.street1}</div>
                        <div>${result.suggested.city}, ${result.suggested.state} ${result.suggested.zip}</div>
                    </div>
                </div>
                <button class="btn btn-primary mt-3" onclick="ShippingApp.acceptSuggested(${JSON.stringify(result.suggested).replace(/"/g, '&quot;')})">
                    Accept Suggested Address
                </button>
            `;
        }

        container.innerHTML = html;
    },

    // Accept suggested address
    acceptSuggested(suggested) {
        document.getElementById('val-name').value = suggested.name || '';
        document.getElementById('val-street').value = suggested.street1;
        document.getElementById('val-city').value = suggested.city;
        document.getElementById('val-state').value = suggested.state;
        document.getElementById('val-zip').value = suggested.zip;

        this.showSuccess('Address updated with suggestion');
    },

    // Load history
    async loadHistory() {
        try {
            const response = await axios.get(`${this.config.apiUrl}/history`);

            if (response.data.success) {
                this.state.history = response.data.data;
                this.renderHistory(response.data.data);
            }

        } catch (error) {
            console.error('Error loading history:', error);
            this.renderHistory([]);
        }
    },

    // Render history
    renderHistory(history) {
        const container = document.getElementById('history-table-container');

        if (history.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="bi bi-inbox fs-1"></i>
                    <p class="mt-3">No labels purchased yet</p>
                </div>
            `;
            return;
        }

        let html = `
            <div class="table-responsive">
                <table class="table table-hover history-table">
                    <thead>
                        <tr>
                            <th>Date</th>
                            <th>Tracking</th>
                            <th>Carrier</th>
                            <th>To</th>
                            <th>Cost</th>
                            <th>Actions</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        history.forEach(label => {
            const date = new Date(label.created_at).toLocaleDateString();
            const to = label.to_address ? `${label.to_address.name || 'Unknown'}, ${label.to_address.city}, ${label.to_address.state}` : 'N/A';

            html += `
                <tr>
                    <td>${date}</td>
                    <td><span class="text-monospace">${label.tracking_number}</span></td>
                    <td>
                        <span class="badge badge-provider bg-secondary">${label.provider}</span><br>
                        <small class="text-muted">${label.carrier} - ${label.service}</small>
                    </td>
                    <td>${to}</td>
                    <td>$${parseFloat(label.cost).toFixed(2)}</td>
                    <td>
            `;

            if (label.google_drive_link) {
                html += `
                    <a href="${label.google_drive_link}" target="_blank" class="btn btn-sm btn-outline-primary me-1" title="Open in Google Drive">
                        <i class="bi bi-cloud-download"></i>
                    </a>
                `;
            }

            html += `
                        <button class="btn btn-sm btn-outline-success" onclick='ShippingApp.copyShipment(${JSON.stringify(label).replace(/'/g, "\\'")})' title="Ship Again">
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                    </td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
        `;

        container.innerHTML = html;
    },

    // Copy shipment details
    copyShipment(label) {
        // Fill in the rates form with previous shipment data
        if (label.to_address) {
            document.getElementById('to-name').value = label.to_address.name || '';
            document.getElementById('to-street').value = label.to_address.street1 || '';
            document.getElementById('to-city').value = label.to_address.city || '';
            document.getElementById('to-state').value = label.to_address.state || '';
            document.getElementById('to-zip').value = label.to_address.zip || '';
        }

        // Switch to rates tab
        const ratesTab = document.getElementById('rates-tab');
        ratesTab.click();

        this.showSuccess('Shipment details copied! Update package dimensions and compare rates.');
    },

    // Save to history
    async saveToHistory(labelData) {
        try {
            await axios.post(`${this.config.apiUrl}/history`, labelData);
        } catch (error) {
            console.error('Error saving to history:', error);
        }
    },

    // UI helpers
    showLoading(message = 'Processing...') {
        document.getElementById('loading-message').textContent = message;
        const modal = new bootstrap.Modal(document.getElementById('loadingModal'));
        modal.show();
    },

    hideLoading() {
        const modal = bootstrap.Modal.getInstance(document.getElementById('loadingModal'));
        if (modal) modal.hide();
    },

    showError(message) {
        alert(`Error: ${message}`);
    },

    showSuccess(message) {
        alert(message);
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    ShippingApp.init();
});
