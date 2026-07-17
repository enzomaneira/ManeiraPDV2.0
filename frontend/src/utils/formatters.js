export const formatCurrency = (value) => {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  }).format(value);
};

export const formatDate = (dateString) => {
  return new Date(dateString).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
};

export const formatFullDate = (dateString) => {
  return new Date(dateString).toLocaleString('pt-BR');
};

export const formatTime = (dateString) => {
    if (!dateString) return '--:--';
    const date = new Date(dateString);
    return date.toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit'
    });
};
