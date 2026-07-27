"""
DM AI OS — Commercial SaaS & Admin HTML UI (Fase 20 / Commercial)
===================================================================
Provides high-aesthetic web interfaces for:
1. Public Checkout & Pricing (Stripe + Mercado Pago ARS converter)
2. Super Admin Login & Dashboard (/admin/login & /admin/dashboard)
3. Mercado Pago Proof Submission Modal & Admin Approvals
"""

def get_commercial_checkout_html() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DM AI OS — Planes & Suscripción Commercial SaaS</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #070b14;
            --bg-card: rgba(15, 23, 42, 0.75);
            --accent-cyan: #38bdf8;
            --accent-green: #34d399;
            --accent-purple: #a855f7;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body {
            background: var(--bg-dark);
            color: var(--text-main);
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 40px 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .header { text-align: center; margin-bottom: 40px; }
        .header h1 { font-size: 2.5rem; color: var(--accent-cyan); margin-bottom: 10px; }
        .grid { display: flex; gap: 20px; flex-wrap: wrap; justify-content: center; max-width: 1000px; }
        .card {
            background: var(--bg-card);
            border: 1px solid rgba(56, 189, 248, 0.2);
            border-radius: 16px;
            padding: 30px;
            width: 300px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            backdrop-filter: blur(10px);
        }
        .card.featured { border-color: var(--accent-cyan); box-shadow: 0 0 20px rgba(56,189,248,0.2); }
        .price { font-size: 2rem; font-weight: 700; margin: 15px 0; color: #fff; }
        .btn-stripe {
            background: linear-gradient(135deg, #6366f1, #4f46e5);
            color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 600; cursor: pointer; margin-bottom: 10px; text-decoration: none; text-align: center; display: block;
        }
        .btn-mp {
            background: linear-gradient(135deg, #009ee3, #0073a5);
            color: white; border: none; padding: 12px; border-radius: 8px; font-weight: 600; cursor: pointer; width: 100%;
        }
        /* Modal */
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); justify-content: center; align-items: center; }
        .modal-content { background: #0f172a; border: 1px solid var(--accent-cyan); border-radius: 12px; padding: 30px; max-width: 450px; width: 90%; }
        input, select { width: 100%; padding: 10px; margin: 10px 0; background: #1e293b; border: 1px solid #334155; color: white; border-radius: 6px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>DM AI OS Commercial Platform</h1>
        <p style="color: var(--text-muted);">Sistema Operativo de Empleados Digitales Autónomos</p>
    </div>

    <div class="grid">
        <div class="card">
            <div>
                <h3>Starter</h3>
                <div class="price">USD $29 <span style="font-size:1rem; font-weight:400;">/ mes</span></div>
                <p style="color: var(--text-muted);">Ideal para emprendedores y autónomos individuales.</p>
            </div>
            <div>
                <a href="https://buy.stripe.com/9B68wQ5WMdF6gYsbCe8AE01" target="_blank" class="btn-stripe">Suscribirme con tarjeta (Stripe)</a>
                <button class="btn-mp" onclick="openMPModal('starter', 29)">Pagar con Mercado Pago</button>
            </div>
        </div>

        <div class="card featured">
            <div>
                <span style="background: var(--accent-cyan); color: #000; padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700;">MÁS POPULAR</span>
                <h3>Professional</h3>
                <div class="price">USD $99 <span style="font-size:1rem; font-weight:400;">/ mes</span></div>
                <p style="color: var(--text-muted);">Suite completa de 20 Empleados Digitales Autónomos.</p>
            </div>
            <div>
                <a href="https://buy.stripe.com/9B68wQ5WMdF6gYsbCe8AE01" target="_blank" class="btn-stripe">Suscribirme con tarjeta (Stripe)</a>
                <button class="btn-mp" onclick="openMPModal('professional', 99)">Pagar con Mercado Pago</button>
            </div>
        </div>
    </div>

    <!-- Modal Mercado Pago -->
    <div id="mpModal" class="modal">
        <div class="modal-content">
            <h3 style="color: var(--accent-cyan); margin-top:0;">Pago con Mercado Pago (Argentina)</h3>
            <p><strong>Plan:</strong> <span id="mpPlanName">Professional</span> (USD $<span id="mpUsd">99</span>)</p>
            <p style="background: rgba(52,211,153,0.1); color: var(--accent-green); padding: 10px; border-radius: 6px;">
                <strong>Equivalente ARS:</strong> $<span id="mpArs">123,750</span> ARS
            </p>
            <div style="font-size: 0.9rem; color: var(--text-muted); margin-bottom: 15px;">
                <strong>Alias:</strong> monetiza.dm<br>
                <strong>CVU:</strong> 0000003100044063397420<br>
                <strong>Titular:</strong> Daniel Alberto Morales
            </div>
            <input type="email" id="userEmail" placeholder="Tu Email para la cuenta SaaS" required>
            <input type="text" id="opNumber" placeholder="Número de Operación de MP" required>
            <button class="btn-mp" onclick="submitMPProof()" style="margin-top:10px;">Ya realicé la transferencia</button>
            <button onclick="closeMPModal()" style="background:transparent; border:none; color:var(--text-muted); width:100%; margin-top:10px; cursor:pointer;">Cancelar</button>
        </div>
    </div>

    <script>
        let currentPlan = 'professional';
        async function openMPModal(plan, usd) {
            currentPlan = plan;
            document.getElementById('mpPlanName').innerText = plan.toUpperCase();
            document.getElementById('mpUsd').innerText = usd;
            const res = await fetch('/v1/billing/mp-details?plan_id=' + plan);
            const data = await res.json();
            document.getElementById('mpArs').innerText = data.amount_ars.toLocaleString('es-AR');
            document.getElementById('mpModal').style.display = 'flex';
        }
        function closeMPModal() { document.getElementById('mpModal').style.display = 'none'; }

        async function submitMPProof() {
            const email = document.getElementById('userEmail').value;
            const op = document.getElementById('opNumber').value;
            if(!email || !op) return alert('Por favor ingresa tu email y número de operación');

            const res = await fetch('/v1/billing/submit-mp-proof', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ user_email: email, plan_id: currentPlan, operation_number: op })
            });
            const data = await res.json();
            alert(data.message || 'Comprobante recibido');
            closeMPModal();
        }
    </script>
</body>
</html>"""


def get_admin_dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>DM AI OS — Super Admin Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        body { background: #0f172a; color: #f8fafc; font-family: 'Inter', sans-serif; padding: 30px; margin: 0; }
        h1 { color: #38bdf8; }
        .card { background: #1e293b; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #334155; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #334155; }
        th { background: #0f172a; color: #38bdf8; }
        .btn-approve { background: #34d399; color: #000; border: none; padding: 6px 12px; border-radius: 4px; font-weight: 600; cursor: pointer; }
        .btn-reject { background: #f87171; color: #000; border: none; padding: 6px 12px; border-radius: 4px; font-weight: 600; cursor: pointer; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 700; }
        .badge-active { background: rgba(52,211,153,0.2); color: #34d399; }
        .badge-pending { background: rgba(251,191,36,0.2); color: #fbbf24; }
    </style>
</head>
<body>
    <h1>DM AI OS — Super Admin Control Panel</h1>
    <p style="color: #94a3b8;">Acceso exclusivo Super Admin — Gestión de Tenants, Pagos & Platform Modules</p>

    <div class="card">
        <h3>Transacciones & Comprobantes Pendientes (Mercado Pago / Stripe)</h3>
        <table>
            <thead>
                <tr>
                    <th>Tx ID</th><th>Tenant / Email</th><th>Plan</th><th>Método</th><th>Monto</th><th>Operación</th><th>Estado</th><th>Acciones</th>
                </tr>
            </thead>
            <tbody id="txTable">
                <tr><td colspan="8">Cargando transacciones...</td></tr>
            </tbody>
        </table>
    </div>

    <div class="card">
        <h3>SaaS Subscriptions & Tenants</h3>
        <table>
            <thead>
                <tr><th>Tenant ID</th><th>Email</th><th>Plan</th><th>Método</th><th>Estado</th><th>Activado</th></tr>
            </thead>
            <tbody id="subTable">
                <tr><td colspan="6">Cargando suscripciones...</td></tr>
            </tbody>
        </table>
    </div>

    <script>
        const token = localStorage.getItem('admin_token');
        if(!token) window.location.href = '/owner/login';

        async function loadAdminData() {
            const headers = { 'Authorization': 'Bearer ' + token };
            const resTx = await fetch('/v1/owner/transactions', { headers });
            if(resTx.status === 401) window.location.href = '/owner/login';
            const txs = await resTx.json();

            let txHtml = '';
            txs.forEach(tx => {
                const isPending = tx.status === 'PENDING_REVIEW';
                txHtml += `<tr>
                    <td>${tx.transaction_id}</td>
                    <td>${tx.user_email}</td>
                    <td>${tx.plan}</td>
                    <td>${tx.payment_method}</td>
                    <td>${tx.amount_ars ? '$' + tx.amount_ars + ' ARS' : '$' + tx.amount_usd + ' USD'}</td>
                    <td>${tx.operation_number || '-'}</td>
                    <td><span class="badge ${isPending ? 'badge-pending' : 'badge-active'}">${tx.status}</span></td>
                    <td>
                        ${isPending ? `<button class="btn-approve" onclick="approveTx('${tx.transaction_id}')">Aprobar</button>
                                       <button class="btn-reject" onclick="rejectTx('${tx.transaction_id}')">Rechazar</button>` : 'N/A'}
                    </td>
                </tr>`;
            });
            document.getElementById('txTable').innerHTML = txHtml;

            const resSub = await fetch('/v1/owner/subscriptions', { headers });
            const subs = await resSub.json();
            let subHtml = '';
            subs.forEach(s => {
                subHtml += `<tr>
                    <td>${s.tenant_id}</td>
                    <td>${s.user_email}</td>
                    <td>${s.plan}</td>
                    <td>${s.payment_method || '-'}</td>
                    <td><span class="badge badge-active">${s.status}</span></td>
                    <td>${s.activated_at || '-'}</td>
                </tr>`;
            });
            document.getElementById('subTable').innerHTML = subHtml;
        }

        async function approveTx(txId) {
            await fetch('/v1/owner/transactions/' + txId + '/approve', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token } });
            loadAdminData();
        }

        async function rejectTx(txId) {
            await fetch('/v1/owner/transactions/' + txId + '/reject', { method: 'POST', headers: { 'Authorization': 'Bearer ' + token } });
            loadAdminData();
        }

        loadAdminData();
    </script>
</body>
</html>"""


def get_admin_login_html() -> str:
    return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <title>DM AI OS — Super Admin Login</title>
    <style>
        body { background: #070b14; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #0f172a; padding: 40px; border-radius: 12px; border: 1px solid #38bdf8; width: 320px; text-align: center; }
        input { width: 100%; padding: 10px; margin: 15px 0; background: #1e293b; border: 1px solid #334155; color: white; border-radius: 6px; box-sizing: border-box; }
        button { background: #38bdf8; color: black; border: none; padding: 12px; width: 100%; font-weight: bold; border-radius: 6px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="login-box">
        <h2 style="color:#38bdf8;">Super Admin Access</h2>
        <input type="password" id="adminPassword" placeholder="Contraseña de Administrador">
        <button onclick="loginAdmin()">Ingresar al Panel</button>
    </div>
    <script>
        async function loginAdmin() {
            const password = document.getElementById('adminPassword').value;
            const res = await fetch('/v1/owner/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ password })
            });
            if(res.ok) {
                const data = await res.json();
                localStorage.setItem('admin_token', data.access_token);
                window.location.href = '/owner/dashboard';
            } else {
                alert('Contraseña incorrecta');
            }
        }
    </script>
</body>
</html>"""

