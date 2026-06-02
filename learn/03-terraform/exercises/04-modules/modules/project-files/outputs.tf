output "files_created" {
  description = "Paths to all files created by this module"
  value       = [local_file.readme.filename, local_file.config.filename]
}
