document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('bedGeneratorForm');
    const generateButton = document.getElementById('generateButton');
    const buttonText = document.getElementById('buttonText');
    const dnaLoader = document.getElementById('dnaLoader');

    loadPanelsFromJSON();

    // Add event listeners
    const eventListeners = {
        'panelDropdown': { event: 'change', handler: updateIdentifiers },
        'includeAmber': { event: 'change', handler: updateIdentifiers },
        'includeRed': { event: 'change', handler: updateIdentifiers },
        'searchPanel': { event: 'keyup', handler: filterPanels },
        'bedFile': { event: 'change', handler: handleBedFileUpload },
        'csvFile': { event: 'change', handler: handleCsvFileUpload }
    };

    Object.entries(eventListeners).forEach(([id, { event, handler }]) => {
        document.getElementById(id).addEventListener(event, handler);
    });

    // Add event listener for form submission
    form.addEventListener('submit', function(event) {
        event.preventDefault();

        var assembly = document.getElementById('assembly').value;

        var include5UTR = document.getElementById('include5UTR').checked;
        var include3UTR = document.getElementById('include3UTR').checked;

        // Clear the file inputs before submitting the form
        document.getElementById('bedFile').value = '';
        document.getElementById('csvFile').value = '';

        // Add this line to capture the initial query
        var initialQuery = {
            identifiers: document.getElementById('identifiers').value,
            coordinates: document.getElementById('coordinates').value,
            assembly: assembly,
            include5UTR: include5UTR,
            include3UTR: include3UTR
        };

        // Modify the payload to include the initial query
        var payload = {
            identifiers: document.getElementById('identifiers').value.split(/[\s,]+/).filter(Boolean),
            coordinates: document.getElementById('coordinates').value.trim(),
            assembly: assembly,
            include5UTR: include5UTR,
            include3UTR: include3UTR,
            initial_query: initialQuery  // Send as an object, not a string
        };

        fetch('/bed_generator/bulk_process', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = '/bed_generator/results';
            } else {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An unexpected error occurred.');
        })
        .finally(() => {
            // Enable the button and revert it back to its original state
            generateButton.disabled = false;
            generateButton.classList.remove('loading');
            buttonText.style.display = 'inline';
            dnaLoader.style.display = 'none';
            dnaLoader.innerHTML = ''; // Clear the DNA loader
        });
    });

    document.getElementById('panelDropdown').addEventListener('change', updateIdentifiers);
});

// Other functions
function loadPanelsFromJSON() {
    return fetch('/bed_generator/panels')
        .then(response => response.json())
        .then(data => {
            console.log('Loaded panel data:', data);  // Add this for debugging
            updatePanelDropdown(data);
        })
        .catch(error => console.error('Error loading panels from JSON:', error));
}

function refreshPanels() {
    console.log("Starting panel refresh");
    var refreshButton = document.querySelector('.refresh-button');
    var buttonText = refreshButton.querySelector('.button-text');
    var loadingSpinner = refreshButton.querySelector('.loading-spinner');

    buttonText.style.display = 'none';
    loadingSpinner.style.display = 'inline-block';

    fetch('/bed_generator/refresh_panels')
        .then(response => {
            console.log("Received response:", response);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Received data:", data);
            updatePanelDropdown(data);
        })
        .catch(error => {
            console.error('Error refreshing panels:', error);
            alert('Failed to refresh panels. Please check the console for more details.');
        })
        .finally(() => {
            console.log("Refresh operation completed");
            buttonText.style.display = 'inline';
            loadingSpinner.style.display = 'none';
        });
}

function updatePanelDropdown(data) {
    var select = document.getElementById('panelDropdown');
    select.innerHTML = '<option value="">Select a panel...</option>';
    
    if (Array.isArray(data)) {
        // If data is an array, assume it's the old format (just panels)
        data.forEach(panel => {
            var option = new Option(panel.full_name || panel.name, panel.id);
            select.add(option);
        });
    } else if (data && Array.isArray(data.panels)) {
        // If data is an object with a panels array, use the new format
        data.panels.forEach(panel => {
            var option = new Option(panel.full_name || panel.name, panel.id);
            select.add(option);
        });
        if (data.last_updated) {
            document.getElementById('lastUpdated').textContent = 'Last updated: ' + new Date(data.last_updated).toLocaleString();
        }
    } else {
        console.error('Unexpected data format:', data);
        alert('Unexpected data format received from server.');
    }
}

function filterPanels() {
    var input = document.getElementById('searchPanel');
    var filter = input.value.toUpperCase();
    var select = document.getElementById('panelDropdown');
    var options = select.options;

    for (var i = 1; i < options.length; i++) {
        var txtValue = options[i].textContent || options[i].innerText;
        if (txtValue.toUpperCase().indexOf(filter) > -1) {
            options[i].style.display = "";
        } else {
            options[i].style.display = "none";
        }
    }
}

function updateIdentifiers() {
    const panelDropdown = document.getElementById('panelDropdown');
    const selectedOption = panelDropdown.options[panelDropdown.selectedIndex];
    const panelId = selectedOption.value;
    const panelName = selectedOption.text;
    console.log('Selected panel ID:', panelId);
    console.log('Selected panel name:', panelName);
    console.log('Panel dropdown value:', panelDropdown.value);

    const includeAmber = document.getElementById('includeAmber').checked;
    const includeRed = document.getElementById('includeRed').checked;
    const panelLoadingSpinner = document.getElementById('panelLoadingSpinner');

    if (!panelId) {
        console.log('No panel selected, loading panels');
        return loadPanelsFromJSON();
    }

    panelDropdown.disabled = true;
    panelLoadingSpinner.style.display = 'inline-block';

    fetch(`/bed_generator/get_genes_by_panel/${encodeURIComponent(panelId)}`)
        .then(response => response.json())
        .then(data => {
            console.log('Received gene data:', data);
            const geneList = data.gene_list || [];
            console.log('Gene list:', geneList);

            const filteredGenes = geneList.filter(gene => {
                if (includeAmber && gene.confidence === '2') return true;
                if (includeRed && gene.confidence === '1') return true;
                return gene.confidence === '3';
            });

            const coloredGenes = filteredGenes.map(gene => {
                const colorMap = { '3': 'green', '2': 'orange', '1': 'red' };
                const color = colorMap[gene.confidence] || '';
                return `<span style="color: ${color};">${gene.symbol}</span>`;
            });

            console.log('Filtered and colored genes:', coloredGenes);
            document.getElementById('identifiers').value = coloredGenes.map(gene => gene.replace(/<[^>]+>/g, '')).join(', ');
            console.log('Set identifiers value:', document.getElementById('identifiers').value);
        })
        .catch(error => console.error('Error fetching gene list:', error))
        .finally(() => {
            panelDropdown.disabled = false;
            panelLoadingSpinner.style.display = 'none';
        });
}

function handleBedFileUpload(event) {
    const files = event.target.files;
    let allCoordinates = [];

    for (let file of files) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const contents = e.target.result;
            const lines = contents.split('\n');
            for (let line of lines) {
                const parts = line.trim().split('\t');
                if (parts.length >= 3) {
                    allCoordinates.push(`${parts[0]}:${parts[1]}-${parts[2]}`);
                }
            }
            // Update the coordinates textarea after processing each file
            document.getElementById('coordinates').value = allCoordinates.join('\n');
        };
        reader.readAsText(file);
    }
}

function handleCsvFileUpload(event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            const contents = e.target.result;
            const identifiers = contents.split(/[\s,]+/).filter(Boolean);
            document.getElementById('identifiers').value = identifiers.join(', ');
        };
        reader.readAsText(file);
    }
}

// Log when the script has finished loading
console.log('Script loaded');

document.getElementById('bedGeneratorForm').addEventListener('submit', function(e) {
    var button = document.getElementById('generateButton');
    var spinner = document.getElementById('spinner');
    
    button.style.display = 'none';
    spinner.classList.remove('d-none');
});
