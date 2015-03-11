#!/usr/bin/env python
"""
Licensed to the Apache Software Foundation (ASF) under one
or more contributor license agreements.  See the NOTICE file
distributed with this work for additional information
regarding copyright ownership.  The ASF licenses this file
to you under the Apache License, Version 2.0 (the
"License"); you may not use this file except in compliance
with the License.  You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

"""

from resource_management import *
import os

def setup_conf_dir(name=None): # 'master' or 'tserver' or 'monitor' or 'gc' or 'tracer' or 'client'
  import params

  # create the conf directory
  Directory( params.conf_dir,
      mode=0750,
      owner = params.accumulo_user,
      group = params.user_group,
      recursive = True
  )

  if name == 'client':
    dest_conf_dir = params.conf_dir

    # create a site file for client processes
    configs = {}
    configs.update(params.config['configurations']['accumulo-site'])
    if "instance.secret" in configs:
      configs.pop("instance.secret")
    if "trace.token.property.password" in configs:
      configs.pop("trace.token.property.password")
    XmlConfig("accumulo-site.xml",
              conf_dir = dest_conf_dir,
              configurations = configs,
              configuration_attributes=params.config['configuration_attributes']['accumulo-site'],
              owner = params.accumulo_user,
              group = params.user_group,
              mode = 0644
    )

    # create env file
    File(format("{dest_conf_dir}/accumulo-env.sh"),
         mode=0644,
         group=params.user_group,
         owner=params.accumulo_user,
         content=InlineTemplate(params.env_sh_template)
    )
  else:
    dest_conf_dir = params.server_conf_dir
    # create server conf directory
    Directory( params.server_conf_dir,
               mode=0700,
               owner = params.accumulo_user,
               group = params.user_group,
               recursive = True
    )
    # create a site file for server processes
    configs = {}
    configs.update(params.config['configurations']['accumulo-site'])
    configs["instance.secret"] = params.config['configurations']['accumulo-env']['instance_secret']
    configs["trace.token.property.password"] = params.trace_password
    XmlConfig( "accumulo-site.xml",
               conf_dir = dest_conf_dir,
               configurations = configs,
               configuration_attributes=params.config['configuration_attributes']['accumulo-site'],
               owner = params.accumulo_user,
               group = params.user_group,
               mode = 0600
    )

    # create pid dir
    Directory( params.pid_dir,
               owner = params.accumulo_user,
               group = params.user_group,
               recursive = True
    )

    # create log dir
    Directory (params.log_dir,
               owner = params.accumulo_user,
               group = params.user_group,
               recursive = True
    )

    # create env file
    File(format("{dest_conf_dir}/accumulo-env.sh"),
         mode=0644,
         group=params.user_group,
         owner=params.accumulo_user,
         content=InlineTemplate(params.server_env_sh_template)
    )

  # create client.conf file
  configs = {}
  configs["instance.name"] = params.instance_name
  configs["instance.zookeeper.host"] = params.config['configurations']['accumulo-site']['instance.zookeeper.host']
  PropertiesFile(format("{dest_conf_dir}/client.conf"),
                 properties = configs,
                 owner = params.accumulo_user,
                 group = params.user_group
  )

  # create log4j.properties files
  if (params.log4j_props != None):
    File(format("{params.conf_dir}/log4j.properties"),
         mode=0644,
         group=params.user_group,
         owner=params.accumulo_user,
         content=params.log4j_props
    )
  else:
    File(format("{params.conf_dir}/log4j.properties"),
         mode=0644,
         group=params.user_group,
         owner=params.hbase_user
    )

  # create logging configuration files
  accumulo_TemplateConfig("auditLog.xml", dest_conf_dir)
  accumulo_TemplateConfig("generic_logger.xml", dest_conf_dir)
  accumulo_TemplateConfig("monitor_logger.xml", dest_conf_dir)
  accumulo_StaticFile("accumulo-metrics.xml", dest_conf_dir)

  # create host files
  accumulo_StaticFile("tracers", dest_conf_dir)
  accumulo_StaticFile("gc", dest_conf_dir)
  accumulo_StaticFile("monitor", dest_conf_dir)
  accumulo_StaticFile("slaves", dest_conf_dir)
  accumulo_StaticFile("masters", dest_conf_dir)

  # metrics configuration
  if params.has_metric_collector:
    accumulo_TemplateConfig( "hadoop-metrics2-accumulo.properties", dest_conf_dir)

  # other server setup
  if name == 'master':
    params.HdfsDirectory(format("/user/{params.accumulo_user}"),
                         action="create_delayed",
                         owner=params.accumulo_user,
                         mode=0700
    )
    params.HdfsDirectory(format("{params.parent_dir}"),
                         action="create_delayed",
                         owner=params.accumulo_user,
                         mode=0700
    )
    params.HdfsDirectory(None, action="create")
    passfile = format("{params.exec_tmp_dir}/pass")
    try:
      File(passfile,
           mode=0600,
           group=params.user_group,
           owner=params.accumulo_user,
           content=InlineTemplate('{{root_password}}\n'
                                  '{{root_password}}\n')
      )
      Execute( format("cat {passfile} | {params.daemon_script} init "
                      "--instance-name {params.instance_name} "
                      "--clear-instance-name "
                      ">{params.log_dir}/accumulo-init.out "
                      "2>{params.log_dir}/accumulo-init.err"),
               not_if=as_user(format("{params.kinit_cmd} "
                                     "{params.hadoop_bin_dir}/hadoop --config "
                                     "{params.hadoop_conf_dir} fs -stat "
                                     "{params.instance_volumes}"),
                              params.accumulo_user),
               user=params.accumulo_user)
    finally:
      os.remove(passfile)

  if name == 'tracer':
    create_user(params.trace_user, params.trace_password)
    create_user(params.smoke_test_user, params.smoke_test_password)

def create_user(user, password):
  import params
  rpassfile = format("{params.exec_tmp_dir}/pass0")
  passfile = format("{params.exec_tmp_dir}/pass")
  cmdfile = format("{params.exec_tmp_dir}/cmds")
  try:
    File(cmdfile,
         mode=0600,
         group=params.user_group,
         owner=params.accumulo_user,
         content=InlineTemplate(format("createuser {user}\n"
                                       "grant -s System.CREATE_TABLE -u {user}\n"))
    )
    File(rpassfile,
         mode=0600,
         group=params.user_group,
         owner=params.accumulo_user,
         content=InlineTemplate('{{root_password}}\n')
    )
    File(passfile,
         mode=0600,
         group=params.user_group,
         owner=params.accumulo_user,
         content=InlineTemplate(format("{params.root_password}\n"
                                       "{password}\n"
                                       "{password}\n"))
    )
    Execute( format("cat {passfile} | {params.daemon_script} shell -u root "
                    "-f {cmdfile}"),
             not_if=as_user(format("cat {rpassfile} | "
                                   "{params.daemon_script} shell -u root "
                                   "-e \"userpermissions -u {user}\""),
                            params.accumulo_user),
             user=params.accumulo_user)
  finally:
    try_remove(rpassfile)
    try_remove(passfile)
    try_remove(cmdfile)

def try_remove(file):
  try:
    os.remove(file)
  except:
    pass

# create file 'name' from template
def accumulo_TemplateConfig(name, dest_conf_dir, tag=None):
  import params

  TemplateConfig( format("{dest_conf_dir}/{name}"),
      owner = params.accumulo_user,
      group = params.user_group,
      template_tag = tag
  )

# create static file 'name'
def accumulo_StaticFile(name, dest_conf_dir):
  import params

  File(format("{dest_conf_dir}/{name}"),
    mode=0644,
    group=params.user_group,
    owner=params.accumulo_user,
    content=StaticFile(name)
  )