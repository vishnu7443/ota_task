import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, UserPlus } from "lucide-react";
import { DesktopAdminLayout } from "@/components/layouts/DesktopAdminLayout";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth-context";
import { iamApi, type IamManagedUser } from "@/lib/api";
import { formatDateTimeIst } from "@/lib/money";

export function AdminUserManagementPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const canManageUsers = user?.role_code === "FACTORY_ADMIN" || user?.role_code === "OWNER";

  const [showCreate, setShowCreate] = useState(false);
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [roleCode, setRoleCode] = useState("SALESMAN");
  const [password, setPassword] = useState("");
  const [employeeCode, setEmployeeCode] = useState("");
  const [territory, setTerritory] = useState("");

  const [editUser, setEditUser] = useState<IamManagedUser | null>(null);
  const [editRole, setEditRole] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [editReason, setEditReason] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const rolesQuery = useQuery({
    queryKey: ["iam-roles"],
    queryFn: () => iamApi.getRoles(),
  });

  const usersQuery = useQuery({
    queryKey: ["iam-users"],
    queryFn: () => iamApi.getUsers(),
  });

  const createMut = useMutation({
    mutationFn: () =>
      iamApi.createUser({
        username,
        full_name: fullName,
        phone: phone || null,
        role_code: roleCode,
        password,
        employee_code: roleCode === "SALESMAN" ? employeeCode || null : null,
        territory: roleCode === "SALESMAN" ? territory || null : null,
      }),
    onSuccess: (created) => {
      setErrorMsg(null);
      setFeedback(`Created user '${created.username}' with role ${created.role_name}.`);
      setShowCreate(false);
      setUsername("");
      setFullName("");
      setPhone("");
      setPassword("");
      setEmployeeCode("");
      setTerritory("");
      void qc.invalidateQueries({ queryKey: ["iam-users"] });
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  const updateMut = useMutation({
    mutationFn: () =>
      iamApi.updateUser(editUser!.id, {
        role_code: editRole,
        is_active: editActive,
        reason: editReason,
      }),
    onSuccess: (updated) => {
      setErrorMsg(null);
      setFeedback(`Updated governance permissions for '${updated.username}' and recorded audit event.`);
      setEditUser(null);
      setEditReason("");
      void qc.invalidateQueries({ queryKey: ["iam-users"] });
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  return (
    <DesktopAdminLayout
      title="Users & Role Governance"
      subtitle="Role-based access control directory & audit-tracked role/status modifications"
      actions={
        canManageUsers ? (
          <Button size="sm" onClick={() => setShowCreate((v) => !v)}>
            <UserPlus className="h-4 w-4" />
            {showCreate ? "Hide Form" : "Provision User"}
          </Button>
        ) : undefined
      }
    >
      <div className="space-y-6">
        {feedback && (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {feedback}
          </div>
        )}
        {errorMsg && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMsg}
          </div>
        )}

        {showCreate && canManageUsers && (
          <Card>
            <CardHeader>
              <CardTitle>Create New User Account</CardTitle>
              <CardDescription>
                Credentials are bcrypt-hashed and automatically excluded from all audit log payloads
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Username *</label>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="e.g. salesman_c" className="mt-1" />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Full Name *</label>
                <Input value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Display name" className="mt-1" />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Phone</label>
                <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91-..." className="mt-1" />
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Role *</label>
                <select
                  value={roleCode}
                  onChange={(e) => setRoleCode(e.target.value)}
                  className="mt-1 flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
                >
                  {(rolesQuery.data ?? []).map((r) => (
                    <option key={r.id} value={r.code}>
                      {r.name} ({r.code})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs font-semibold text-muted-foreground">Initial Password (min 8 chars) *</label>
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className="mt-1" />
              </div>
              {roleCode === "SALESMAN" && (
                <>
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Salesman Employee Code</label>
                    <Input value={employeeCode} onChange={(e) => setEmployeeCode(e.target.value)} placeholder="SM-003" className="mt-1" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-muted-foreground">Territory</label>
                    <Input value={territory} onChange={(e) => setTerritory(e.target.value)} placeholder="Coimbatore Zone" className="mt-1" />
                  </div>
                </>
              )}
              <div className="sm:col-span-2 lg:col-span-3 flex justify-end">
                <Button onClick={() => createMut.mutate()} disabled={createMut.isPending}>
                  {createMut.isPending ? "Creating..." : "Create User"}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-primary" />
              Registered System Users ({usersQuery.data?.length ?? 0})
            </CardTitle>
            <CardDescription>
              Every role reassignment or account activation/deactivation requires a documented reason
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2">Username</th>
                  <th className="py-2">Full Name</th>
                  <th className="py-2">Role</th>
                  <th className="py-2">Status</th>
                  <th className="py-2">Last Login (IST)</th>
                  <th className="py-2">Created (IST)</th>
                  {canManageUsers && <th className="py-2 text-right">Governance</th>}
                </tr>
              </thead>
              <tbody>
                {(usersQuery.data ?? []).map((u) => (
                  <tr key={u.id} className="border-b last:border-b-0">
                    <td className="py-2.5 font-mono text-xs font-semibold">{u.username}</td>
                    <td className="py-2.5">{u.full_name}</td>
                    <td className="py-2.5">
                      <span className="font-medium">{u.role_name}</span>
                      <span className="ml-1.5 text-xs text-muted-foreground">({u.role_code})</span>
                    </td>
                    <td className="py-2.5">
                      <StatusBadge status={u.is_active ? "ACTIVE" : "CANCELLED"} />
                    </td>
                    <td className="py-2.5 text-xs text-muted-foreground">{formatDateTimeIst(u.last_login_at)}</td>
                    <td className="py-2.5 text-xs text-muted-foreground">{formatDateTimeIst(u.created_at)}</td>
                    {canManageUsers && (
                      <td className="py-2.5 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setEditUser(u);
                            setEditRole(u.role_code);
                            setEditActive(u.is_active);
                            setEditReason("");
                          }}
                        >
                          Edit Role / Status
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>

        {editUser && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
            <Card className="w-full max-w-md">
              <CardHeader>
                <CardTitle>Modify User Access: {editUser.full_name}</CardTitle>
                <CardDescription>@{editUser.username}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">Assigned Role</label>
                  <select
                    value={editRole}
                    onChange={(e) => setEditRole(e.target.value)}
                    className="mt-1 flex h-11 w-full rounded-lg border border-input bg-card px-3 text-sm"
                  >
                    {(rolesQuery.data ?? []).map((r) => (
                      <option key={r.id} value={r.code}>
                        {r.name}
                      </option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={editActive}
                    onChange={(e) => setEditActive(e.target.checked)}
                  />
                  Account Active (unchecked revokes login access immediately)
                </label>
                <div>
                  <label className="text-xs font-semibold text-muted-foreground">
                    Mandatory Audit Reason (min 5 chars) *
                  </label>
                  <Input
                    value={editReason}
                    onChange={(e) => setEditReason(e.target.value)}
                    placeholder="Reason for role or status change..."
                    className="mt-1"
                  />
                </div>
                <div className="flex justify-end gap-2">
                  <Button variant="outline" onClick={() => setEditUser(null)}>
                    Cancel
                  </Button>
                  <Button onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
                    {updateMut.isPending ? "Saving..." : "Apply & Audit"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </DesktopAdminLayout>
  );
}
