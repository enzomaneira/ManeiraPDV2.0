import KanbanColumn from '../components/KanbanColumn';
import OrderCard from '../components/OrderCard';
import { ChefHat, CheckCircle, Bike, AlertCircle, Navigation, Store, Package, MapPin } from 'lucide-react';
import { boardColumns } from '../utils/deliveryStages';

const ICONS = {
    alert: <AlertCircle />, chef: <ChefHat />, check: <CheckCircle />, bike: <Bike />,
    navigation: <Navigation />, store: <Store />, package: <Package />, map: <MapPin />,
};

export default function OrdersPage({ orders, config, onSelectOrder }) {
    const detailed = Boolean(config.detailedDeliveryStatus);
    const columns = boardColumns(orders, { detailed, autoAccept: config.autoAccept });

    return (
        // Modo detalhado: colunas mais estreitas, alinhadas à esquerda e com
        // rolagem horizontal (centralizar esconderia as primeiras colunas).
        <div className={detailed
            ? 'flex h-full gap-4 w-max'
            : 'flex h-full gap-6 justify-center min-w-[900px] mx-auto max-w-[1600px]'}>
            {columns.map(column => (
                <KanbanColumn key={column.id} title={column.title} count={column.orders.length}
                    colorTheme={column.theme} icon={ICONS[column.icon]} compact={detailed}>
                    {column.orders.map(order => (
                        <OrderCard key={order.id} order={order} onClick={() => onSelectOrder(order)} />
                    ))}
                </KanbanColumn>
            ))}
        </div>
    );
}
