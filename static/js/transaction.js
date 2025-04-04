function handleServiceChange(serviceId) {
    if (!serviceId) {
        document.getElementById('variablePriceSection').style.display = 'none';
        return;
    }

    fetch(`/api/service/${serviceId}`)
        .then(response => response.json())
        .then(service => {
            const variablePriceSection = document.getElementById('variablePriceSection');
            if (service.variable_pricing) {
                variablePriceSection.style.display = 'block';
                // Set min and max price if available
                const variablePriceInput = document.getElementById('variable_price');
                if (service.min_price) variablePriceInput.min = service.min_price;
                if (service.max_price) variablePriceInput.max = service.max_price;
            } else {
                variablePriceSection.style.display = 'none';
            }
        })
        .catch(error => console.error('Error fetching service details:', error));
}