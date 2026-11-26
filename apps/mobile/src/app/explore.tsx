import { useState, useEffect, useCallback } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { VaakApi, CartData } from '@/services/api';

export default function CartScreen() {
  const [cart, setCart] = useState<CartData>({
    items: [],
    currency: 'INR',
    subtotal: 0,
    total_items: 0,
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const fetchCart = useCallback(async () => {
    try {
      setLoading(true);
      const data = await VaakApi.getCart();
      setCart(data);
    } catch (err) {
      console.error('Failed to load cart:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCart();
  }, [fetchCart]);

  const handleUpdateQuantity = async (itemId: string, newQty: number) => {
    try {
      const updated = await VaakApi.updateCartItem(itemId, newQty);
      setCart(updated);
    } catch (err) {
      console.error('Failed to update quantity:', err);
    }
  };

  const handleRemove = async (itemId: string) => {
    try {
      const updated = await VaakApi.deleteCartItem(itemId);
      setCart(updated);
    } catch (err) {
      console.error('Failed to remove item:', err);
    }
  };

  const handleExplicitConfirmation = () => {
    if (cart.items.length === 0) {
      Alert.alert('Cart is empty', 'Add some grocery items using voice or search first.');
      return;
    }

    Alert.alert(
      'Explicit Order Confirmation',
      `You are confirming an order for ${cart.total_items} items totaling ₹${cart.subtotal.toFixed(
        2
      )} via Zepto.\n\nNever silently place an order without your review.\n\nProceed with simulated order placement?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Confirm & Place Order',
          onPress: async () => {
            setIsSubmitting(true);
            setTimeout(() => {
              setIsSubmitting(false);
              Alert.alert(
                'Order Received by Zepto (Simulated)',
                `Order total ₹${cart.subtotal.toFixed(2)} recorded.\nEstimated delivery: 10 mins.`
              );
            }, 1200);
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Your Grocery Cart</Text>
        <TouchableOpacity onPress={fetchCart} style={styles.refreshButton}>
          <Text style={styles.refreshText}>↻ Refresh</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color="#6366F1" />
          <Text style={styles.loadingText}>Fetching cart from Vaak engine...</Text>
        </View>
      ) : cart.items.length === 0 ? (
        <View style={styles.centerContainer}>
          <Text style={styles.emptyCartIcon}>🛒</Text>
          <Text style={styles.emptyTitle}>Your cart is empty</Text>
          <Text style={styles.emptySubtitle}>
            Go to the Voice tab and speak: "I need milk, eggs, and bread"
          </Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          {cart.items.map((item) => (
            <View key={item.id} style={styles.itemCard}>
              <View style={styles.itemHeader}>
                <View style={styles.itemMain}>
                  <Text style={styles.itemName}>{item.name}</Text>
                  {item.pack_size && <Text style={styles.itemPack}>{item.pack_size}</Text>}
                  <Text style={styles.itemPrice}>₹{item.unit_price.toFixed(2)} / unit</Text>
                </View>
                <TouchableOpacity onPress={() => handleRemove(item.id)} style={styles.deleteButton}>
                  <Text style={styles.deleteText}>✕</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.itemFooter}>
                <View style={styles.quantityControls}>
                  <TouchableOpacity
                    style={styles.qtyButton}
                    onPress={() => handleUpdateQuantity(item.id, item.quantity - 1)}
                  >
                    <Text style={styles.qtyButtonText}>-</Text>
                  </TouchableOpacity>
                  <Text style={styles.qtyText}>{item.quantity}</Text>
                  <TouchableOpacity
                    style={styles.qtyButton}
                    onPress={() => handleUpdateQuantity(item.id, item.quantity + 1)}
                  >
                    <Text style={styles.qtyButtonText}>+</Text>
                  </TouchableOpacity>
                </View>
                <Text style={styles.totalPrice}>₹{(item.quantity * item.unit_price).toFixed(2)}</Text>
              </View>
            </View>
          ))}

          {/* Bill Summary */}
          <View style={styles.billCard}>
            <Text style={styles.billTitle}>Bill Summary</Text>
            <View style={styles.billRow}>
              <Text style={styles.billLabel}>Item Total</Text>
              <Text style={styles.billValue}>₹{cart.subtotal.toFixed(2)}</Text>
            </View>
            <View style={styles.billRow}>
              <Text style={styles.billLabel}>Delivery Fee</Text>
              <Text style={[styles.billValue, { color: '#10B981' }]}>FREE</Text>
            </View>
            <View style={styles.divider} />
            <View style={styles.billRow}>
              <Text style={styles.grandTotalLabel}>To Pay</Text>
              <Text style={styles.grandTotalValue}>₹{cart.subtotal.toFixed(2)}</Text>
            </View>
          </View>

          {/* Philosophy Note */}
          <View style={styles.philosophyBox}>
            <Text style={styles.philosophyText}>
              🛡️ <Text style={{ fontWeight: '700' }}>Voice-first, never voice-only</Text>: We require your visual review and explicit tap confirmation before placing any order.
            </Text>
          </View>

          {/* Confirm Order Button */}
          <TouchableOpacity
            style={styles.confirmButton}
            onPress={handleExplicitConfirmation}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.confirmButtonText}>
                Confirm Order (₹{cart.subtotal.toFixed(2)}) →
              </Text>
            )}
          </TouchableOpacity>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F172A',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#1E293B',
  },
  title: {
    fontSize: 20,
    fontWeight: '800',
    color: '#F8FAFC',
  },
  refreshButton: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    backgroundColor: '#1E293B',
    borderRadius: 8,
  },
  refreshText: {
    color: '#94A3B8',
    fontSize: 12,
  },
  scrollContent: {
    padding: 20,
    paddingBottom: 40,
  },
  centerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  loadingText: {
    marginTop: 12,
    color: '#94A3B8',
    fontSize: 14,
  },
  emptyCartIcon: {
    fontSize: 54,
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#F8FAFC',
    marginBottom: 6,
  },
  emptySubtitle: {
    fontSize: 13,
    color: '#94A3B8',
    textAlign: 'center',
    lineHeight: 20,
  },
  itemCard: {
    backgroundColor: '#1E293B',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#334155',
  },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  itemMain: {
    flex: 1,
    marginRight: 10,
  },
  itemName: {
    fontSize: 15,
    fontWeight: '700',
    color: '#F8FAFC',
  },
  itemPack: {
    fontSize: 12,
    color: '#94A3B8',
    marginTop: 2,
  },
  itemPrice: {
    fontSize: 13,
    color: '#CBD5E1',
    marginTop: 4,
  },
  deleteButton: {
    padding: 6,
  },
  deleteText: {
    fontSize: 14,
    color: '#94A3B8',
  },
  itemFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 14,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#334155',
  },
  quantityControls: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F172A',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#334155',
  },
  qtyButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  qtyButtonText: {
    color: '#F8FAFC',
    fontSize: 16,
    fontWeight: '700',
  },
  qtyText: {
    color: '#F8FAFC',
    fontSize: 14,
    fontWeight: '700',
    paddingHorizontal: 8,
  },
  totalPrice: {
    fontSize: 16,
    fontWeight: '800',
    color: '#10B981',
  },
  billCard: {
    backgroundColor: '#1E293B',
    borderRadius: 14,
    padding: 16,
    marginTop: 12,
    borderWidth: 1,
    borderColor: '#334155',
  },
  billTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#F8FAFC',
    marginBottom: 12,
    textTransform: 'uppercase',
  },
  billRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  billLabel: {
    fontSize: 13,
    color: '#94A3B8',
  },
  billValue: {
    fontSize: 13,
    fontWeight: '600',
    color: '#F8FAFC',
  },
  divider: {
    height: 1,
    backgroundColor: '#334155',
    marginVertical: 10,
  },
  grandTotalLabel: {
    fontSize: 16,
    fontWeight: '800',
    color: '#F8FAFC',
  },
  grandTotalValue: {
    fontSize: 18,
    fontWeight: '800',
    color: '#10B981',
  },
  philosophyBox: {
    backgroundColor: 'rgba(99, 102, 241, 0.1)',
    borderRadius: 10,
    padding: 12,
    marginVertical: 16,
    borderWidth: 1,
    borderColor: 'rgba(99, 102, 241, 0.3)',
  },
  philosophyText: {
    fontSize: 12,
    color: '#A5B4FC',
    lineHeight: 18,
  },
  confirmButton: {
    backgroundColor: '#10B981',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    shadowColor: '#10B981',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 4,
  },
  confirmButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
});
