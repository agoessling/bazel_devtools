local workspace = assert(vim.env.BAZEL_DEVTOOLS_WORKSPACE)

local contracts = {
  { file = "python/greeting.py", marker = "pyrightconfig.json" },
  { file = "cpp/greeting.cc", marker = "compile_commands.json" },
  { file = "rust/greeting.rs", marker = "rust-project.json" },
}

for _, contract in ipairs(contracts) do
  local file = workspace .. "/" .. contract.file
  vim.cmd.edit(vim.fn.fnameescape(file))
  local root = vim.fs.root(0, { contract.marker })
  assert(root == workspace, contract.file .. " resolved to unexpected root " .. tostring(root))
  local decoded = vim.json.decode(table.concat(vim.fn.readfile(workspace .. "/" .. contract.marker), "\n"))
  assert(type(decoded) == "table", contract.marker .. " is not valid JSON")
end

vim.cmd.quitall({ bang = true })
