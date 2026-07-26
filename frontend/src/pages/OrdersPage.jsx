import KanbanColumn from '../components/KanbanColumn';
import OrderCard from '../components/OrderCard';
import { ChefHat, CheckCircle, Bike, AlertCircle } from 'lucide-react';

export default function OrdersPage({ orders, config, onSelectOrder }) {
    const getOrdersByStatus = (status) => orders.filter(o => o.status === status);

    return (
        <div className="flex h-full gap-6 justify-center min-w-[900px] mx-auto max-w-[1600px]">
            {!config.autoAccept && (
                <KanbanColumn title="Aprovação Pendente" count={getOrdersByStatus('PENDING').length + getOrdersByStatus('NEW').length} colorTheme="blue" icon={<AlertCircle />}>
                    {[...getOrdersByStatus('PENDING'), ...getOrdersByStatus('NEW')].map(order => (
                        <OrderCard key={order.id} order={order} color="blue" onClick={() => onSelectOrder(order)} />
                    ))}
                </KanbanColumn>
            )}

            <KanbanColumn title="Em Preparo" count={getOrdersByStatus('PREPARING').length} colorTheme="orange" icon={<ChefHat />}>
                {getOrdersByStatus('PREPARING').map(order => (
                    <OrderCard key={order.id} order={order} color="orange" onClick={() => onSelectOrder(order)} />
                ))}
            </KanbanColumn>

            <KanbanColumn title="Pronto p/ Entrega" count={getOrdersByStatus('READY').length} colorTheme="green" icon={<CheckCircle />}>
                {getOrdersByStatus('READY').map(order => (
                    <OrderCard key={order.id} order={order} color="green" onClick={() => onSelectOrder(order)} />
                ))}
            </KanbanColumn>

            <KanbanColumn title="Entregas" count={getOrdersByStatus('DISPATCHED').length} colorTheme="purple" icon={<Bike />}>
                {getOrdersByStatus('DISPATCHED').map(order => (
                    <OrderCard key={order.id} order={order} color="purple" onClick={() => onSelectOrder(order)} />
                ))}
            </KanbanColumn>
        </div>
    );
}