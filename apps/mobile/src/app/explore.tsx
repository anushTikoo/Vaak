import { useState, useEffect, useCallback } from 'react';
import {
  StyleSheet,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  Alert,
  Linking,
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
  const [paymentMethod, setPaymentMethod] = useState<'UPI' | 'COD'>('UPI');
  const [activePaymentLink, setActivePaymentLink] = useState<string | null>(null);
  const [activeOrderCode, setActiveOrderCode] = useState<string | null>(null);

  const fetchCart = useCallback(async (refresh: boolean = false) => {
    try {
      setLoading(true);
      const data = await VaakApi.getCart(refresh);
      setCart(data);
    } catch (err) {
      console.error('Failed to load cart:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // Fetch cached cart on mount (does not spam Zepto MCP)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCart(false);
  }, [fetchCart]);

  const handleUpdateQuantity = async (item: { id: string; product_id: string }, newQty: number) => {
    try {
      const targetId = item.product_id || item.id;
      const updated = await VaakApi.updateCartItem(targetId, newQty);
      setCart(updated);
    } catch (err) {
      console.error('Failed to update quantity:', err);
    }
  };

  const handleRemove = async (item: { id: string; product_id: string }) => {
    try {
      const targetId = item.product_id || item.id;
      const updated = await VaakApi.deleteCartItem(targetId);
      setCart(updated);
    } catch (err) {
      console.error('Failed to remove item:', err);
    }
  };

  const executeOrder = async (method: 'UPI' | 'COD') => {
    try {
      setIsSubmitting(true);
      const result = await VaakApi.checkoutOrder(true, method);
      const emptyCart = await VaakApi.getCart(true);
      setCart(emptyCart);

      if (method === 'UPI' && result.payment_link) {
        setActivePaymentLink(result.payment_link);
        const displayCode = result.order_code || result.order_id || 'ZEP-UPI';
        setActiveOrderCode(displayCode);

        Alert.alert(
          '⚡ UPI Order Initiated!',
          `Order Code: ${displayCode}\n\n` +
            `Total Payable: ₹${result.to_pay.toFixed(2)}\n\n` +
            `We are redirecting you to Zepto's secure Juspay checkout page. You can pay via Google Pay, PhonePe, Paytm, or enter your UPI ID.\n\n` +
            `Safe Note: Zero money is deducted until you authorize with your secret UPI PIN.`,
          [
            {
              text: 'Open UPI Payment ↗',
              onPress: async () => {
                try {
                  await Linking.openURL(result.payment_link!);
                } catch (linkErr) {
                  console.warn('Could not open payment link:', linkErr);
                }
              },
            },
            { text: 'Later', style: 'cancel' },
          ]
        );

        // Also trigger direct redirect on device
        try {
          await Linking.openURL(result.payment_link);
        } catch {
          // Alert above provides fallback action button
        }
      } else {
        Alert.alert(
          '⚡ Order Placed on Zepto!',
          `Order #${result.order_code || result.order_id || 'ZEP-CONFIRMED'}\n\n` +
            `Delivering to: ${result.delivery_address || 'Home'}\n` +
            `Total to Pay: ₹${result.to_pay.toFixed(2)} (Cash on Delivery)\n` +
            `Estimated Arrival: ~${result.eta_minutes || 10} minutes.`
        );
      }
    } catch (err: any) {
      console.error('Failed to place order:', err);
      Alert.alert(
        'Order Notice',
        err.message || 'Could not place order with Zepto. Please check items and try again.'
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleExplicitConfirmation = () => {
    if (cart.items.length === 0) {
      Alert.alert('Cart is empty', 'Add some grocery items using voice or search first.');
      return;
    }

    if (paymentMethod === 'UPI') {
      Alert.alert(
        '⚠️ WARNING: Initiating Real Order',
        `You are about to initiate a REAL order for ${cart.total_items} items totaling ₹${cart.subtotal.toFixed(
          2
        )} with Zepto Dark Store.\n\n` +
          `• Payment Mode: UPI / Online Payment (Juspay Gateway)\n` +
          `• Safe Guarantee: Zero money is deducted until you enter your secret UPI PIN in your UPI app (Google Pay, PhonePe, Paytm).\n` +
          `• Redirects to secure UPI payment page.\n\n` +
          `Do you want to proceed and open the UPI payment page?`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Yes, Proceed to UPI Payment →',
            onPress: () => executeOrder('UPI'),
          },
        ]
      );
    } else {
      Alert.alert(
        '⚠️ WARNING: Placing Real Order Immediately',
        `You are about to IMMEDIATELY place an active real order for ${cart.total_items} items totaling ₹${cart.subtotal.toFixed(
          2
        )} with Zepto.\n\n` +
          `• Payment Mode: Cash on Delivery (COD)\n` +
          `• A delivery partner will be dispatched to your address immediately (~10 mins).\n\n` +
          `Are you sure you want to place this order now?`,
        [
          { text: 'Cancel', style: 'cancel' },
          {
            text: 'Yes, Place Real Order (COD)',
            style: 'destructive',
            onPress: () => executeOrder('COD'),
          },
        ]
      );
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Your Grocery Cart</Text>
        <TouchableOpacity onPress={() => fetchCart(true)} style={styles.refreshButton}>
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
                <TouchableOpacity onPress={() => handleRemove(item)} style={styles.deleteButton}>
                  <Text style={styles.deleteText}>✕</Text>
                </TouchableOpacity>
              </View>

              <View style={styles.itemFooter}>
                <View style={styles.quantityControls}>
                  <TouchableOpacity
                    style={styles.qtyButton}
                    onPress={() => handleUpdateQuantity(item, item.quantity - 1)}
                  >
                    <Text style={styles.qtyButtonText}>-</Text>
                  </TouchableOpacity>
                  <Text style={styles.qtyText}>{item.quantity}</Text>
                  <TouchableOpacity
                    style={styles.qtyButton}
                    onPress={() => handleUpdateQuantity(item, item.quantity + 1)}
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

          {/* Payment Method Selector */}
          <View style={styles.paymentMethodCard}>
            <Text style={styles.paymentMethodTitle}>Select Payment Method</Text>
            <View style={styles.paymentMethodOptions}>
              <TouchableOpacity
                style={[
                  styles.paymentOptionButton,
                  paymentMethod === 'UPI' && styles.paymentOptionSelected,
                ]}
                onPress={() => setPaymentMethod('UPI')}
              >
                <Text style={styles.paymentOptionIcon}>⚡</Text>
                <View style={styles.paymentOptionTextContainer}>
                  <Text
                    style={[
                      styles.paymentOptionLabel,
                      paymentMethod === 'UPI' && styles.paymentOptionTextSelected,
                    ]}
                  >
                    UPI / Online (Juspay)
                  </Text>
                  <Text style={styles.paymentOptionSub}>Google Pay, PhonePe, Paytm, BHIM</Text>
                </View>
                {paymentMethod === 'UPI' && <Text style={styles.checkIcon}>✓</Text>}
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.paymentOptionButton,
                  paymentMethod === 'COD' && styles.paymentOptionSelected,
                ]}
                onPress={() => setPaymentMethod('COD')}
              >
                <Text style={styles.paymentOptionIcon}>💵</Text>
                <View style={styles.paymentOptionTextContainer}>
                  <Text
                    style={[
                      styles.paymentOptionLabel,
                      paymentMethod === 'COD' && styles.paymentOptionTextSelected,
                    ]}
                  >
                    Cash on Delivery (COD)
                  </Text>
                  <Text style={styles.paymentOptionSub}>Pay cash to delivery partner</Text>
                </View>
                {paymentMethod === 'COD' && <Text style={styles.checkIcon}>✓</Text>}
              </TouchableOpacity>
            </View>
          </View>

          {/* Active UPI Payment Banner */}
          {activePaymentLink && (
            <View style={styles.upiActiveBanner}>
              <Text style={styles.upiActiveTitle}>⚡ UPI Payment Link Ready</Text>
              <Text style={styles.upiActiveSubtitle}>
                Order #{activeOrderCode} initiated. Tap below to complete payment via UPI app:
              </Text>
              <TouchableOpacity
                style={styles.openUpiButton}
                onPress={() => Linking.openURL(activePaymentLink)}
              >
                <Text style={styles.openUpiButtonText}>Open UPI Payment Page ↗</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* Philosophy Note */}
          <View style={styles.philosophyBox}>
            <Text style={styles.philosophyText}>
              🛡️ <Text style={{ fontWeight: '700' }}>Voice-first, never voice-only</Text>: We require your visual review and explicit tap confirmation before placing any order.
            </Text>
          </View>

          {/* Confirm Order Button */}
          <TouchableOpacity
            style={[
              styles.confirmButton,
              paymentMethod === 'UPI' ? styles.confirmButtonUpi : styles.confirmButtonCod,
            ]}
            onPress={handleExplicitConfirmation}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.confirmButtonText}>
                {paymentMethod === 'UPI'
                  ? `⚡ Confirm & Pay with UPI (₹${cart.subtotal.toFixed(2)}) →`
                  : `💵 Confirm Order with COD (₹${cart.subtotal.toFixed(2)}) →`}
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
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 4,
  },
  confirmButtonUpi: {
    backgroundColor: '#6366F1',
    shadowColor: '#6366F1',
  },
  confirmButtonCod: {
    backgroundColor: '#10B981',
    shadowColor: '#10B981',
  },
  confirmButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  paymentMethodCard: {
    backgroundColor: '#1E293B',
    borderRadius: 14,
    padding: 16,
    marginTop: 14,
    borderWidth: 1,
    borderColor: '#334155',
  },
  paymentMethodTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#F8FAFC',
    marginBottom: 12,
    textTransform: 'uppercase',
  },
  paymentMethodOptions: {
    gap: 10,
  },
  paymentOptionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#0F172A',
    borderRadius: 12,
    padding: 14,
    borderWidth: 1.5,
    borderColor: '#334155',
  },
  paymentOptionSelected: {
    borderColor: '#6366F1',
    backgroundColor: 'rgba(99, 102, 241, 0.12)',
  },
  paymentOptionIcon: {
    fontSize: 22,
    marginRight: 12,
  },
  paymentOptionTextContainer: {
    flex: 1,
  },
  paymentOptionLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: '#E2E8F0',
  },
  paymentOptionTextSelected: {
    color: '#A5B4FC',
  },
  paymentOptionSub: {
    fontSize: 11,
    color: '#94A3B8',
    marginTop: 2,
  },
  checkIcon: {
    fontSize: 18,
    fontWeight: '800',
    color: '#6366F1',
    marginLeft: 8,
  },
  upiActiveBanner: {
    backgroundColor: 'rgba(99, 102, 241, 0.15)',
    borderRadius: 12,
    padding: 16,
    marginTop: 14,
    borderWidth: 1.5,
    borderColor: '#6366F1',
  },
  upiActiveTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#A5B4FC',
    marginBottom: 4,
  },
  upiActiveSubtitle: {
    fontSize: 12,
    color: '#CBD5E1',
    lineHeight: 18,
    marginBottom: 12,
  },
  openUpiButton: {
    backgroundColor: '#6366F1',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
  },
  openUpiButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
});
